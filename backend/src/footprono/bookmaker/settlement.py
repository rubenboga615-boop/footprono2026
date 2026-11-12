"""Règlement des paris, dès que le résultat est connu.

Chaque sélection est réglée par **le même calcul que ses probabilités** : le
match réel est une distribution qui donne 100 % au score observé (mi-temps et
fin de match, ou corners, cartons, tirs), passée dans ``derive_markets`` ou
``count_markets``. Handicaps au quart, remboursements, combinés dans un même
match : aucune règle à part, donc aucune divergence possible entre ce qui a
été prédit et ce qui est réglé.

Résultat provisoire (API-Football, dès la fin du match) puis confirmé par
football-data : si le score change, les paris concernés des 7 derniers jours
sont **réglés à nouveau** (écart crédité ou débité, avec une note).
"""

import functools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import numpy as np
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from footprono.accounts import service as accounts
from footprono.accounts.models import Wallet
from footprono.bookmaker import montante
from footprono.bookmaker.models import Bet, BetSelection
from footprono.engine.counts import booking_points_markets, count_markets
from footprono.engine.markets import Selection, derive_markets
from footprono.engine.scores import ScoreDistribution
from footprono.football.models import (
    DataSource,
    LiveSnapshot,
    Match,
    MatchStatus,
    MatchTeamStats,
    StatPeriod,
    Team,
)
from footprono.ingestion.sources.api_football import UNPLAYED_STATUSES
from footprono.notifications import service as notifications

if TYPE_CHECKING:
    from footprono.notifications.push import FcmSender

HALF_TIME_MARKETS = ("HT_", "HTFT", "HIGHEST_HALF")
COUNT_PREFIXES = {
    "CORNERS": "corners",
    "CARDS": "cards",
    "SHOTS": "shots",
    "SOT": "shots_on_target",
}
# Règlement pendant le match (plan du 10/11/2026, étape 2) : une sélection est réglée dès
# que plus aucun but (corner, carton) ne peut changer son résultat. Seuls comptent les
# relevés pris il y a au moins EARLY_DELAY : un but annulé par la VAR dans ce délai n'est
# jamais pris en compte (au-delà, le contrôle par le score final corrige le règlement).
EARLY_DELAY = timedelta(minutes=4)
# Temps réglementaire seulement : en prolongation, le score compte des buts qui ne valent pas
# pour les paris (réglés sur 90 minutes) ; on attend alors la fin du match.
EARLY_STATUSES = frozenset({"1H", "HT", "2H"})
HALF_TIME_OVER = frozenset({"HT", "2H"})
GOALS_AHEAD = 9  # buts possibles encore, par équipe, pour juger qu'un résultat est acquis
COUNTS_AHEAD = 16  # corners, cartons ou tirs possibles encore, par équipe
# Statistiques d'API-Football (noms des relevés) pour les marchés de comptage.
LIVE_COUNT_TYPES = {
    "corners": ("Corner Kicks",),
    "cards": ("Yellow Cards", "Red Cards"),
    "yellow_cards": ("Yellow Cards",),
    "red_cards": ("Red Cards",),
    "shots": ("Total Shots",),
    "shots_on_target": ("Shots on Goal",),
}
# Match reporté ou annulé : sélection remboursée passé ce délai après le coup d'envoi prévu.
VOID_AFTER = timedelta(hours=48)
RESETTLE_WINDOW = timedelta(days=7)


@dataclass(frozen=True)
class Grade:
    result: str  # win, half_win, push, half_loss, loss
    factor: Decimal  # multiplicateur de la mise pour cette sélection


def _point_mass(shape: tuple[int, ...], at: tuple[int, ...]) -> np.ndarray:
    joint = np.zeros([max(s, a + 1) for s, a in zip(shape, at, strict=True)])
    joint[at] = 1.0
    return joint


def _grade(sel: Selection, odds: Decimal) -> Grade:
    if sel.win > 0.5:
        return Grade("win", odds)
    if sel.half_win > 0.5:
        return Grade("half_win", (1 + odds) / 2)
    if sel.push > 0.5:
        return Grade("push", Decimal(1))
    if sel.half_loss > 0.5:
        return Grade("half_loss", Decimal("0.5"))
    return Grade("loss", Decimal(0))


def goals_grade(match: Match, market: str, key: str) -> Selection | None:
    """Règlement d'un marché de buts ; None si une donnée manque (score à la mi-temps)."""
    if match.home_goals is None or match.away_goals is None:
        return None
    ht = (match.home_goals_ht, match.away_goals_ht)
    needs_ht = market.startswith(HALF_TIME_MARKETS)
    if needs_ht and (ht[0] is None or ht[1] is None):
        return None
    # Marchés du match complet : le score à la mi-temps n'intervient pas.
    hh, ha = int(ht[0] or 0), int(ht[1] or 0)
    joint = _point_mass((7, 7, 11, 11), (hh, ha, match.home_goals, match.away_goals))
    return derive_markets(ScoreDistribution(joint=joint)).get(key)


@functools.lru_cache(maxsize=4096)
def _score_selection(home: int, away: int, key: str) -> Selection | None:
    joint = _point_mass((7, 7, 11, 11), (0, 0, home, away))
    return derive_markets(ScoreDistribution(joint=joint)).get(key)


def live_grade(match: Match, market: str, line: str, selection: str) -> str | None:
    """Ce que donnerait la sélection si le match s'arrêtait sur le score actuel (« gagnante pour
    l'instant »), par le même calcul que le règlement. Seulement les marchés du match complet
    en buts : pas la mi-temps, ni les corners, cartons, tirs (pas de compte en direct)."""
    if match.live_home_goals is None or match.live_away_goals is None:
        return None
    if market.startswith(HALF_TIME_MARKETS) or market.split("_")[0] in COUNT_PREFIXES:
        return None
    if market == "BOOKING_POINTS_OU":
        return None
    outcome = _score_selection(
        match.live_home_goals, match.live_away_goals, f"{market}|{line}|{selection}"
    )
    return None if outcome is None else _grade(outcome, Decimal(1)).result


@functools.lru_cache(maxsize=1024)
def _goal_markets(hh: int, ha: int, home: int, away: int) -> dict[str, Selection]:
    joint = _point_mass((7, 7, 11, 11), (hh, ha, home, away))
    return derive_markets(ScoreDistribution(joint=joint))


@functools.lru_cache(maxsize=4096)
def _count_markets(stat: str, home: int, away: int) -> dict[str, Selection]:
    return count_markets(stat, _point_mass((31, 31), (home, away)))


def _settled_whatever(
    outcomes: Callable[[int, int], Selection | None], ahead: int
) -> Selection | None:
    """Le résultat d'une sélection s'il est le même quoi qu'il arrive d'ici la fin (x buts
    de plus d'un côté, y de l'autre) ; None s'il peut encore changer."""
    first: Selection | None = None
    result: str | None = None
    for x in range(ahead):
        for y in range(ahead):
            sel = outcomes(x, y)
            if sel is None:
                return None
            grade = _grade(sel, Decimal(1)).result
            if result is None:
                first, result = sel, grade
            elif grade != result:
                return None
    return first


def early_goals(
    market: str, key: str, score: tuple[int, int], half_time: tuple[int, int] | None
) -> Selection | None:
    """Marché de buts décidé avant la fin : « plus de 2,5 » gagné dès le 3e but, « moins de
    2,5 » perdu, « les deux marquent » gagné dès que les deux ont marqué ; marchés de la
    1re mi-temps dès la pause (``half_time`` connu)."""
    needs_ht = market.startswith(HALF_TIME_MARKETS)
    if needs_ht and half_time is None:
        return None
    hh, ha = half_time or (0, 0)
    if hh > 6 or ha > 6:
        return None
    h, a = max(score[0], hh), max(score[1], ha)

    def outcome(x: int, y: int) -> Selection | None:
        if h + x > 10 or a + y > 10:
            return _goal_markets(hh, ha, min(h + x, 10), min(a + y, 10)).get(key)
        return _goal_markets(hh, ha, h + x, a + y).get(key)

    return _settled_whatever(outcome, GOALS_AHEAD)


def early_counts(stat: str, key: str, counts: tuple[int, int]) -> Selection | None:
    """Marché de comptage décidé avant la fin : « plus de 9,5 corners » gagné au 10e."""
    h, a = counts

    def outcome(x: int, y: int) -> Selection | None:
        return _count_markets(stat, min(h + x, 30), min(a + y, 30)).get(key)

    return _settled_whatever(outcome, COUNTS_AHEAD)


def _live_counts(snap: LiveSnapshot, stat: str) -> tuple[int, int] | None:
    if snap.home_stats is None or snap.away_stats is None:
        return None

    def total(stats: dict[str, Any]) -> int:
        # Compteur absent = 0 (convention d'API-Football, voir MatchTeamStats).
        return sum(int(stats.get(t) or 0) for t in LIVE_COUNT_TYPES[stat])

    try:
        return total(snap.home_stats), total(snap.away_stats)
    except (TypeError, ValueError):
        return None


async def _early_grade(
    session: AsyncSession, match: Match, sel: BetSelection, now: datetime
) -> Grade | None:
    """Règlement d'une sélection pendant le match, sur le dernier relevé assez ancien."""
    snap = await session.scalar(
        select(LiveSnapshot)
        .where(LiveSnapshot.match_id == match.id, LiveSnapshot.taken_at <= now - EARLY_DELAY)
        .order_by(LiveSnapshot.taken_at.desc())
        .limit(1)
    )
    if snap is None or snap.status not in EARLY_STATUSES or match.api_status not in EARLY_STATUSES:
        return None
    if snap.home_goals is None or snap.away_goals is None:
        return None
    # Un but annulé depuis le relevé : le score actuel, plus bas, fait foi.
    score = (
        min(snap.home_goals, match.live_home_goals if match.live_home_goals is not None else 99),
        min(snap.away_goals, match.live_away_goals if match.live_away_goals is not None else 99),
    )
    half_time = None
    if snap.status in HALF_TIME_OVER and match.home_goals_ht is not None:
        half_time = (match.home_goals_ht, match.away_goals_ht or 0)
    key = f"{sel.market}|{sel.line}|{sel.selection}"
    if sel.market == "BOOKING_POINTS_OU":
        return None
    stat = COUNT_PREFIXES.get(sel.market.split("_")[0])
    if stat is not None:
        counts = _live_counts(snap, stat)
        outcome = None if counts is None else early_counts(stat, key, counts)
    else:
        outcome = early_goals(sel.market, key, score, half_time)
    return None if outcome is None else _grade(outcome, sel.odds)


def _count_values(
    match: Match, stats: dict[int, MatchTeamStats], stat: str
) -> tuple[int, int] | None:
    """Corners, cartons, tirs du match : football-data (confirmé) sinon API-Football."""
    fd = {
        "corners": (match.home_corners, match.away_corners),
        "cards": (
            None
            if match.home_yellow_cards is None
            else match.home_yellow_cards + (match.home_red_cards or 0),
            None
            if match.away_yellow_cards is None
            else match.away_yellow_cards + (match.away_red_cards or 0),
        ),
        "yellow_cards": (match.home_yellow_cards, match.away_yellow_cards),
        "red_cards": (match.home_red_cards, match.away_red_cards),
        "shots": (match.home_shots, match.away_shots),
        "shots_on_target": (match.home_shots_on_target, match.away_shots_on_target),
    }[stat]
    if fd[0] is not None and fd[1] is not None and match.result_source == "football_data":
        return int(fd[0]), int(fd[1])
    home, away = stats.get(match.home_team_id), stats.get(match.away_team_id)
    if home is None or away is None:
        return None if fd[0] is None or fd[1] is None else (int(fd[0]), int(fd[1]))

    def value(s: MatchTeamStats) -> int | None:
        if stat == "cards":
            return None if s.yellow_cards is None else s.yellow_cards + (s.red_cards or 0)
        column = {
            "corners": "corners", "yellow_cards": "yellow_cards", "red_cards": "red_cards",
            "shots": "total_shots", "shots_on_target": "shots_on_goal",
        }[stat]  # fmt: skip
        v = getattr(s, column)
        return None if v is None else int(v)

    h, a = value(home), value(away)
    return None if h is None or a is None else (h, a)


def counts_grade(
    match: Match, stats: dict[int, MatchTeamStats], market: str, key: str
) -> Selection | None:
    if market == "BOOKING_POINTS_OU":
        yellow = _count_values(match, stats, "yellow_cards")
        red = _count_values(match, stats, "red_cards")
        if yellow is None or red is None:
            return None
        y = np.zeros(sum(yellow) + 1)
        y[sum(yellow)] = 1
        r = np.zeros(sum(red) + 1)
        r[sum(red)] = 1
        return booking_points_markets(y, r).get(key)
    stat = COUNT_PREFIXES[market.split("_")[0]]
    values = _count_values(match, stats, stat)
    if values is None:
        return None
    return count_markets(stat, _point_mass((31, 31), values)).get(key)


# Libellé de la statistique d'un marché de comptage, pour l'affichage d'un pari réglé.
COUNT_LABELS = {"corners": "corners", "cards": "cartons", "shots": "tirs",
                "shots_on_target": "tirs cadrés"}  # fmt: skip


def count_stat(market: str) -> str | None:
    """Statistique comptée par ce marché (corners, cartons, tirs), None pour un marché de buts."""
    return COUNT_PREFIXES.get(market.split("_")[0])


async def finished_counts(
    session: AsyncSession, pairs: list[tuple[Match, str]]
) -> dict[tuple[int, str], tuple[int, int]]:
    """Corners, cartons ou tirs de chaque match terminé (domicile, extérieur), pour les
    sélections de comptage : un pari « plus de 7,5 corners » s'affiche avec ses corners, pas
    avec le score en buts (essai réel du 06/11/2026)."""
    out: dict[tuple[int, str], tuple[int, int]] = {}
    stats: dict[int, dict[int, MatchTeamStats]] = {}
    for match, market in pairs:
        stat = count_stat(market)
        if stat is None or match.status is not MatchStatus.FINISHED or (match.id, stat) in out:
            continue
        if match.id not in stats:
            stats[match.id] = await _match_stats(session, match.id)
        values = _count_values(match, stats[match.id], stat)
        if values is not None:
            out[(match.id, stat)] = values
    return out


async def _match_stats(session: AsyncSession, match_id: int) -> dict[int, MatchTeamStats]:
    rows = await session.scalars(
        select(MatchTeamStats).where(
            MatchTeamStats.match_id == match_id,
            MatchTeamStats.source == DataSource.API_FOOTBALL,
            MatchTeamStats.period == StatPeriod.FULL,
        )
    )
    return {s.team_id: s for s in rows}


async def grade_selection(session: AsyncSession, sel: BetSelection, now: datetime) -> Grade | None:
    """Résultat d'une sélection ; None tant qu'il n'est pas connu."""
    match = await session.get(Match, sel.match_id)
    assert match is not None
    if match.status is MatchStatus.CANCELLED:
        return Grade("push", Decimal(1))
    if match.status is not MatchStatus.FINISHED:
        planned = match.kickoff_at or datetime.combine(match.match_date, datetime.min.time(), UTC)
        if match.api_status in UNPLAYED_STATUSES and now - planned > VOID_AFTER:
            return Grade("push", Decimal(1))  # reporté ou annulé : remboursé
        # Pendant le match : réglée dès que son résultat ne peut plus changer.
        return await _early_grade(session, match, sel, now)
    key = f"{sel.market}|{sel.line}|{sel.selection}"
    if sel.market.split("_")[0] in COUNT_PREFIXES or sel.market == "BOOKING_POINTS_OU":
        outcome = counts_grade(match, await _match_stats(session, match.id), sel.market, key)
    else:
        outcome = goals_grade(match, sel.market, key)
    if outcome is None:
        return None
    return _grade(outcome, sel.odds)


def bet_outcome(stake: int, grades: list[Grade]) -> tuple[str, int]:
    """Issue et gain d'un pari (arrondi au franc inférieur, comme un bookmaker)."""
    factor = Decimal(1)
    for g in grades:
        factor *= g.factor
    payout = math.floor(Decimal(stake) * factor)
    results = {g.result for g in grades}
    if "loss" in results:
        return "lost", 0
    if results == {"push"}:
        return "push", payout
    if results <= {"win", "push"}:
        return "won", payout
    return "partial", payout


_TITLES = {
    "won": "Pari gagné",
    "lost": "Pari perdu",
    "push": "Pari remboursé",
    "partial": "Pari réglé en partie",
}


async def _bet_name(session: AsyncSession, selections: Sequence[BetSelection]) -> str:
    """« Arsenal - Chelsea » pour un pari simple, « combiné de 3 matchs » sinon."""
    matches = {s.match_id for s in selections}
    if len(matches) != 1:
        return f"combiné de {len(matches)} matchs"
    home, away = aliased(Team), aliased(Team)
    row = (
        await session.execute(
            select(home.name, away.name)
            .select_from(Match)
            .join(home, home.id == Match.home_team_id)
            .join(away, away.id == Match.away_team_id)
            .where(Match.id == next(iter(matches)))
        )
    ).first()
    return f"{row[0]} - {row[1]}" if row else "pari"


def _notify_settled(session: AsyncSession, bet: Bet, name: str) -> None:
    outcome = bet.outcome or "lost"
    if outcome == "lost":
        body = f"{name} : mise de {notifications.money(bet.stake, bet.currency)} perdue."
    else:
        gain = notifications.money(bet.payout or 0, bet.currency)
        body = f"{name} : {gain} crédités sur ton solde."
    notifications.add(
        session, bet.user_id, "bet_settled", _TITLES[outcome], body,
        {"bet_id": bet.id, "outcome": outcome, "payout": bet.payout},
    )  # fmt: skip


# Verrous PostgreSQL du règlement (rendus à la fin de la transaction, même en cas d'erreur).
SETTLE_BETS_LOCK = 7_301_001
SETTLE_COUPONS_LOCK = 7_301_002


async def hold_lock(session: AsyncSession, key: int) -> None:
    """Attend puis tient le verrou ``key`` jusqu'à la fin de la transaction en cours."""
    await session.execute(select(func.pg_advisory_xact_lock(key)))


async def settle_bets(
    session: AsyncSession,
    now: datetime | None = None,
    redis: Redis | None = None,
    push: "FcmSender | None" = None,
) -> dict[str, Any]:
    """Règle les paris ouverts dont le résultat est connu ; revoit les règlements récents.

    Les notifications sont diffusées (``redis``) une fois le règlement validé.
    """
    now = now or datetime.now(UTC)
    report: dict[str, Any] = {"settled": 0, "resettled": 0, "pending": 0}
    # Un seul règlement à la fois (audit de sécurité du 12/11/2026, n° 1) : le suivant attend
    # la fin du premier, puis relit des paris déjà réglés ; payés une seule fois.
    await hold_lock(session, SETTLE_BETS_LOCK)
    open_bets = (await session.scalars(select(Bet).where(Bet.status == "open"))).all()
    recent = (
        await session.scalars(
            select(Bet).where(Bet.status == "settled", Bet.settled_at >= now - RESETTLE_WINDOW)
        )
    ).all()
    for bet in [*open_bets, *recent]:
        selections = (
            await session.scalars(select(BetSelection).where(BetSelection.bet_id == bet.id))
        ).all()
        grades = [await grade_selection(session, s, now) for s in selections]
        lost = any(g is not None and g.result == "loss" for g in grades)
        if not lost and any(g is None for g in grades):
            # Pari pas encore réglé : chaque sélection est notée dès la fin de son match,
            # comme chez un vrai bookmaker (avant : « en attente » jusqu'au dernier match).
            for s, g in zip(selections, grades, strict=True):
                if g is not None:
                    s.result = g.result
            report["pending"] += bet.status == "open"
            continue
        for s, g in zip(selections, grades, strict=True):
            s.result = g.result if g is not None else "pending"
        outcome, payout = (
            ("lost", 0) if lost else bet_outcome(bet.stake, [g for g in grades if g is not None])
        )
        if bet.status == "open":
            bet.status, bet.outcome, bet.payout, bet.settled_at = "settled", outcome, payout, now
            bet.settlements = 1
            if payout:
                await accounts.move(
                    session, bet.user_id, payout, "payout", bet_id=bet.id, note=f"pari {bet.id}"
                )
            _notify_settled(session, bet, await _bet_name(session, selections))
            await montante.on_bet_settled(session, bet)
            report["settled"] += 1
        elif (outcome, payout) != (bet.outcome, bet.payout):
            await _correct(session, bet, outcome, payout, now, await _bet_name(session, selections))
            report["resettled"] += 1
    await session.commit()
    report["notified"] = await notifications.publish_pending(session, redis, push)
    return report


async def _correct(
    session: AsyncSession, bet: Bet, outcome: str, payout: int, now: datetime, name: str
) -> None:
    """Score corrigé après coup : l'écart de gain est crédité ou débité, avec une note.

    Argent fictif : un débit ne peut pas rendre le solde négatif ; il est limité
    au solde disponible (le reste est indiqué dans la note).
    """
    delta = payout - (bet.payout or 0)
    wallet = await session.get(Wallet, bet.user_id, with_for_update=True)
    assert wallet is not None
    applied = max(delta, -wallet.balance)
    note = f"pari {bet.id} réglé à nouveau (score corrigé) : {bet.outcome} → {outcome}"
    if applied != delta:
        note += f" ; {delta - applied} non repris (solde insuffisant)"
    if applied:
        await accounts.move(session, bet.user_id, applied, "correction", bet_id=bet.id, note=note)
    notifications.add(
        session, bet.user_id, "bet_corrected", "Score corrigé",
        f"{name} réglé à nouveau : {_TITLES[outcome].lower()} "
        f"({notifications.money(applied, bet.currency)} sur ton solde).",
        {"bet_id": bet.id, "outcome": outcome, "payout": payout, "delta": applied},
    )  # fmt: skip
    bet.outcome, bet.payout, bet.settled_at = outcome, payout, now
    bet.settlements += 1
