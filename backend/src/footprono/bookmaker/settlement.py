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

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import numpy as np
from redis.asyncio import Redis
from sqlalchemy import select
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
        return None
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
