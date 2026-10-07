"""Coupon intelligent : le marché le plus sûr de chaque match, assemblé en coupon.

Méthode validée hors échantillon (``footprono-engine angles``, docs/MOTEUR.md) :
dans chaque match, parmi les marchés retenus (``rules.automatic``) qui ont
une **vraie cote** jouable, on prend la sélection la plus probable de la
tranche du profil (« sûr » : la plus proche du milieu de sa tranche) ; on
garde ensuite les matchs les plus sûrs, jamais deux sélections d'un même
match (elles sont liées).

- **Sûr** : 75 à 92 % par sélection ; **équilibré** : 60 à 75 % ;
  **audacieux** : 45 à 60 %.
- Probabilité du coupon = produit des probabilités du moteur. Mesuré sur
  2022-2025 : juste pour « équilibré » et « audacieux », prudente (sous-estimée)
  pour « sûr ». Aucune promesse de gain : la cote du bookmaker contient sa
  marge, et le coupon ne bat pas le bookmaker à long terme.
- Chaque sélection est expliquée par des faits (forme, moyennes de la
  saison, confrontations), jamais par une opinion.
- **Grosse cote** : l'utilisateur fixe une cote totale visée. Pour chaque
  profil, on ajoute ses angles du plus probable au moins probable jusqu'à
  atteindre la cote (``target_coupon``), puis on garde le coupon dont la cote
  est la plus proche de la cible. Les sélections sont choisies par leur probabilité seule, jamais
  par l'écart entre le moteur et la cote : chercher « la combinaison la plus
  probable » parmi toutes choisissait les sélections où le moteur contredit le
  plus la cote, c'est-à-dire là où il se trompe le plus souvent (vérifié sur
  les données réelles le 03/10/2026).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from footprono.accounts.models import User
from footprono.bookmaker import service, settlement
from footprono.bookmaker.models import BetSelection
from footprono.bookmaker.rules import automatic
from footprono.bookmaker.smart_models import SmartCoupon
from footprono.core.errors import AppError, NotFoundError
from footprono.football.analysis import match_analysis
from footprono.football.models import Competition, Match, MatchStatus, Season, Team
from footprono.ingestion.live import LIVE_STATUSES
from footprono.notifications import service as notifications


@dataclass(frozen=True)
class Profile:
    label: str
    low: float
    high: float
    # Sélection visée dans la tranche : la plus probable (None) ou la plus proche
    # de cette probabilité. « Sûr » vise le milieu : au plafond (90 %), un coupon
    # de 3 rapportait 1,31 ; au milieu (83 %), 1,66 pour 60 % de réussite,
    # annoncé juste sur 2019-2025 (étude du 02/10/2026, docs/MOTEUR.md).
    target: float | None = None


PROFILES = {
    "sur": Profile("Sûr", 0.75, 0.92, target=0.835),
    "equilibre": Profile("Équilibré", 0.60, 0.75),
    "audacieux": Profile("Audacieux", 0.45, 0.60),
}
PERIODS = {
    "today": "Aujourd'hui",
    "tomorrow": "Demain",
    "3days": "3 prochains jours",
    "weekend": "Ce week-end",
    "week": "7 prochains jours",
    # Toujours des matchs : la prochaine journée, même après une trêve internationale.
    "next": "Prochaine journée",
    "day": "Un seul jour",  # avec ``day``
    "range": "Plusieurs jours",  # avec ``date_from`` et ``date_to`` (inclus)
}
TARGET_PROFILE = "grosse"
TARGET_LABEL = "Grosse cote"
TARGET_MIN, TARGET_MAX = Decimal("2"), Decimal("1000")
NEXT_ROUND_DAYS = 4  # vendredi → lundi
MIN_SIZE, MAX_SIZE = 1, 12
MAX_RANGE_DAYS = 14
MIN_ODDS = Decimal("1.10")  # en dessous, la sélection ne rapporte presque rien
CLOSE_BEFORE_KICKOFF = timedelta(minutes=15)
ALTERNATIVES = 3


def _midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def period_window(
    period: str,
    now: datetime,
    day: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[datetime, datetime]:
    """Début et fin (UTC, heure d'Abidjan) des matchs retenus pour la période."""
    if period not in PERIODS:
        raise AppError(f"période inconnue : {period} ({', '.join(PERIODS)})")
    today = datetime(now.year, now.month, now.day, tzinfo=UTC)
    start = now + CLOSE_BEFORE_KICKOFF
    if period == "day":
        if day is None:
            raise AppError("période « un seul jour » : indique le jour (day=AAAA-MM-JJ)")
        return max(start, _midnight(day)), _midnight(day) + timedelta(days=1)
    if period == "range":
        if date_from is None or date_to is None or date_to < date_from:
            raise AppError("période « plusieurs jours » : indique date_from et date_to (inclus)")
        if (date_to - date_from).days >= MAX_RANGE_DAYS:
            raise AppError(f"période « plusieurs jours » : {MAX_RANGE_DAYS} jours au plus")
        return max(start, _midnight(date_from)), _midnight(date_to) + timedelta(days=1)
    if period == "today":
        return start, today + timedelta(days=1)
    if period == "tomorrow":
        return max(start, today + timedelta(days=1)), today + timedelta(days=2)
    if period == "3days":
        return start, today + timedelta(days=3)
    if period == "week":
        return start, today + timedelta(days=7)
    if period == "next":  # fin fixée par generate, d'après le premier match à venir
        return start, start
    # Ce week-end : samedi et dimanche (le week-end en cours s'il a commencé).
    saturday = today + timedelta(days=(5 - today.weekday()) % 7)
    if today.weekday() == 6:
        saturday = today - timedelta(days=1)
    return max(start, saturday), saturday + timedelta(days=2)


@dataclass(frozen=True)
class Pick:
    match: Match
    home: str
    away: str
    competition: str
    offer: service.Offer
    probability: float


async def _matches(
    session: AsyncSession, start: datetime, end: datetime, competitions: list[str] | None
) -> list[tuple[Match, str, str, str]]:
    home, away = aliased(Team), aliased(Team)
    stmt = (
        select(Match, home.name, away.name, Competition.code)
        .join(home, home.id == Match.home_team_id)
        .join(away, away.id == Match.away_team_id)
        .join(Season, Season.id == Match.season_id)
        .join(Competition, Competition.id == Season.competition_id)
        .where(
            Match.status == MatchStatus.SCHEDULED,
            Match.kickoff_at >= start,
            Match.kickoff_at < end,
            or_(Match.api_status.is_(None), Match.api_status.in_(("NS", "TBD"))),
        )
        .order_by(Match.kickoff_at, Match.id)
    )
    if competitions:
        stmt = stmt.where(Competition.code.in_([c.upper() for c in competitions]))
    return list((await session.execute(stmt)).tuples().all())


async def next_kickoff(
    session: AsyncSession, after: datetime, competitions: list[str] | None = None
) -> datetime | None:
    """Coup d'envoi du premier match à venir (après ``after``)."""
    far = after + timedelta(days=60)
    found = await _matches(session, after, far, competitions)
    return found[0][0].kickoff_at if found else None


_DAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
    "septembre", "octobre", "novembre", "décembre",
)  # fmt: skip


def french_day(d: datetime) -> str:
    return f"{_DAYS[d.weekday()]} {d.day} {_MONTHS[d.month - 1]}"


def choose(profile: Profile, inside: list[Pick]) -> Pick:
    """L'angle du match : le plus probable, ou le plus proche de la cible du profil."""
    if profile.target is None:
        return max(inside, key=lambda pk: pk.probability)
    target = profile.target
    return min(inside, key=lambda pk: (abs(pk.probability - target), -pk.probability))


@dataclass(frozen=True)
class Filters:
    """Restrictions choisies par l'utilisateur (toutes facultatives)."""

    competitions: list[str] | None = None
    after_hour: int | None = None  # coup d'envoi à partir de cette heure (UTC = Abidjan)
    exclude_matches: frozenset[int] = frozenset()
    exclude_teams: frozenset[int] = frozenset()

    def keeps(self, match: Match) -> bool:
        if match.id in self.exclude_matches:
            return False
        if {match.home_team_id, match.away_team_id} & self.exclude_teams:
            return False
        return not (
            self.after_hour is not None
            and match.kickoff_at is not None
            and match.kickoff_at.hour < self.after_hour
        )


async def _candidates(
    session: AsyncSession, match: Match, home: str, away: str, comp: str, now: datetime
) -> list[Pick]:
    """Sélections jouables d'un match : marché retenu, vraie cote, probabilité du moteur."""
    offers = await service.match_offer(session, match.id, now)
    probs = await service.model_probabilities(session, match.id)
    return [
        Pick(match, home, away, comp, offer, p)
        for k, offer in offers.items()
        if (p := probs.get(k)) is not None and automatic(offer.market) and offer.odds >= MIN_ODDS
    ]


def angle(profile: Profile, candidates: list[Pick]) -> Pick | None:
    inside = [pk for pk in candidates if profile.low <= pk.probability < profile.high]
    return choose(profile, inside) if inside else None


async def match_angles(
    session: AsyncSession, match_id: int, now: datetime | None = None
) -> dict[str, Pick | None]:
    """« Les choix du moteur » d'un match : l'angle de chaque profil (ou rien)."""
    now = now or datetime.now(UTC)
    home, away = aliased(Team), aliased(Team)
    row = (
        await session.execute(
            select(Match, home.name, away.name, Competition.code)
            .join(home, home.id == Match.home_team_id)
            .join(away, away.id == Match.away_team_id)
            .join(Season, Season.id == Match.season_id)
            .join(Competition, Competition.id == Season.competition_id)
            .where(Match.id == match_id)
        )
    ).first()
    if row is None:
        return dict.fromkeys(PROFILES)
    match, home_name, away_name, code = row._tuple()
    candidates = await _candidates(session, match, home_name, away_name, code, now)
    return {key: angle(prof, candidates) for key, prof in PROFILES.items()}


async def best_angles(
    session: AsyncSession,
    profile: Profile,
    start: datetime,
    end: datetime,
    now: datetime,
    competitions: list[str] | None = None,
    filters: Filters | None = None,
) -> list[Pick]:
    """L'angle de chaque match (voir ``choose``), du plus sûr au moins sûr."""
    filters = filters or Filters(competitions=competitions)
    picks = []
    for match, home, away, comp in await _matches(session, start, end, filters.competitions):
        if not filters.keeps(match):
            continue
        pick = angle(profile, await _candidates(session, match, home, away, comp, now))
        if pick is not None:
            picks.append(pick)
    picks.sort(key=lambda pk: (-pk.probability, pk.match.kickoff_at, pk.match.id))
    return picks


def target_coupon(ranked: list[Pick], target: Decimal, max_size: int) -> list[Pick]:
    """Les sélections les plus probables (dans l'ordre de ``ranked``) jusqu'à la cote visée.

    Ordre de probabilité pur : choisir une sélection « parce que sa cote suffit » ou
    « parce que le moteur la juge plus probable que sa cote » reviendrait à choisir là
    où le moteur contredit le bookmaker (vérifié le 03/10/2026). Liste vide si la cote
    n'est pas atteinte avec ``max_size`` sélections au plus.
    """
    chosen: list[Pick] = []
    total = Decimal(1)
    for pk in ranked:
        if len(chosen) >= max_size:
            break
        chosen.append(pk)
        total *= pk.offer.odds
        if total >= target:
            return chosen
    return []


# ----------------------------------------------------------------- explications


def _avg(x: float | None) -> str:
    return "—" if x is None else f"{x:.1f}".replace(".", ",")


def _form(results: list[dict[str, Any]]) -> str:
    letters = {"W": "V", "D": "N", "L": "D"}
    return "".join(letters[r["result"]] for r in results) or "—"


def reasons(analysis: dict[str, Any], pick: Pick) -> list[str]:
    """Deux faits au plus qui éclairent la sélection (aucune opinion)."""
    market = pick.offer.market
    sh, sa = analysis["season"]["home"], analysis["season"]["away"]
    home, away = pick.home, pick.away
    out: list[str] = []
    if market.startswith(("CORNERS_",)):
        out.append(f"Corners par match cette saison : {home} {_avg(sh.get('corners'))}, "
                   f"{away} {_avg(sa.get('corners'))}")  # fmt: skip
    elif market.startswith(("SHOTS_", "SOT_")):
        out.append(f"Tirs cadrés par match : {home} {_avg(sh.get('shots_on_target'))}, "
                   f"{away} {_avg(sa.get('shots_on_target'))}")  # fmt: skip
    elif market in ("1X2", "DC", "EH", "AH", "HT_1X2", "DNB", "WIN_TO_NIL"):
        out.append(f"Forme (5 derniers) : {home} {_form(analysis['form']['home'])}, "
                   f"{away} {_form(analysis['form']['away'])}")  # fmt: skip
        out.append(f"Buts marqués / encaissés par match : {home} {_avg(sh.get('goals_for'))} / "
                   f"{_avg(sh.get('goals_against'))}, {away} {_avg(sa.get('goals_for'))} / "
                   f"{_avg(sa.get('goals_against'))}")  # fmt: skip
    else:  # buts : total, par équipe, les deux marquent, clean sheet, mi-temps
        out.append(f"Buts par match (marqués + encaissés) : {home} "
                   f"{_avg(_sum(sh.get('goals_for'), sh.get('goals_against')))}, {away} "
                   f"{_avg(_sum(sa.get('goals_for'), sa.get('goals_against')))}")  # fmt: skip
        if sh.get("xg_for") is not None and sa.get("xg_for") is not None:
            out.append(
                f"xG créés par match : {home} {_avg(sh['xg_for'])}, {away} {_avg(sa['xg_for'])}"
            )
    h2h = analysis["head_to_head"]
    if len(out) < 2 and h2h:
        goals = [sum(int(x) for x in m["score"].split("-")) for m in h2h]
        out.append(f"{len(h2h)} dernières confrontations : {sum(goals) / len(goals):.1f} buts "
                   "par match".replace(".", ","))  # fmt: skip
    return out[:2]


def _sum(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else a + b


def _selection_out(pick: Pick, analysis: dict[str, Any] | None) -> dict[str, Any]:
    m = pick.match
    return {
        "match_id": m.id,
        "home": pick.home,
        "away": pick.away,
        "home_team_id": m.home_team_id,
        "away_team_id": m.away_team_id,
        "competition": pick.competition,
        "kickoff_at": m.kickoff_at,
        "market": pick.offer.market,
        "line": pick.offer.line,
        "selection": pick.offer.selection,
        "odds": pick.offer.odds,
        "bookmaker": pick.offer.bookmaker,
        "label": pick.offer.label,
        "model_probability": round(pick.probability, 4),
        "reasons": reasons(analysis, pick) if analysis else [],
    }


def selection_summary(pick: Pick) -> dict[str, Any]:
    """Une sélection sans ses explications (écran d'un match)."""
    return _selection_out(pick, None)


def summarize(selections: list[Pick]) -> tuple[Decimal, float]:
    total, probability = Decimal(1), 1.0
    for pk in selections:
        total *= pk.offer.odds
        probability *= pk.probability
    return total.quantize(Decimal("0.01")), probability


async def generate(
    session: AsyncSession,
    profile: str,
    period: str,
    size: int,
    *,
    competitions: list[str] | None = None,
    target_odds: Decimal | None = None,
    day: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    after_hour: int | None = None,
    exclude_matches: list[int] | None = None,
    exclude_teams: list[int] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Coupon d'un profil (``size`` sélections) ou Grosse cote (``target_odds``).

    En Grosse cote, ``size`` est le nombre maximum de sélections.
    """
    grosse = profile == TARGET_PROFILE
    if not grosse and profile not in PROFILES:
        raise AppError(f"profil inconnu : {profile} ({', '.join([*PROFILES, TARGET_PROFILE])})")
    if not MIN_SIZE <= size <= MAX_SIZE:
        raise AppError(f"nombre de sélections : {MIN_SIZE} à {MAX_SIZE}")
    if grosse and (target_odds is None or not TARGET_MIN <= target_odds <= TARGET_MAX):
        raise AppError(f"cote visée : de {TARGET_MIN} à {TARGET_MAX}")
    if after_hour is not None and not 0 <= after_hour <= 23:
        raise AppError("heure de début : de 0 à 23")
    now = now or datetime.now(UTC)
    start, end = period_window(period, now, day, date_from, date_to)
    filters = Filters(
        competitions=competitions,
        after_hour=after_hour,
        exclude_matches=frozenset(exclude_matches or ()),
        exclude_teams=frozenset(exclude_teams or ()),
    )
    first = await next_kickoff(session, start, competitions)
    if period == "next" and first is not None:
        day0 = datetime(first.year, first.month, first.day, tzinfo=UTC)
        end = day0 + timedelta(days=NEXT_ROUND_DAYS)
    label = TARGET_LABEL if grosse else PROFILES[profile].label
    period_label = PERIODS[period]
    if period == "day" and day is not None:
        period_label = french_day(_midnight(day))
    out: dict[str, Any] = {
        "profile": profile,
        "profile_label": label,
        "range": None if grosse else [PROFILES[profile].low, PROFILES[profile].high],
        "target_odds": target_odds,
        "period": period,
        "period_label": period_label,
        "size": size,
        "generated_at": now,
        "window": [start, end],
        "coupon": None,
        "alternatives": [],
        "message": None,
    }
    if first is None or first >= end:
        # Aucun match sur la période (trêve internationale, fin de saison) : le dire.
        out["message"] = f"Aucun match prévu pour « {period_label.lower()} »." + (
            f" Prochains matchs à partir du {french_day(first)} : choisis « Prochaine journée »."
            if first is not None
            else " Aucun match à venir au calendrier pour l'instant."
        )
        return out
    if grosse:
        assert target_odds is not None
        # Un coupon par profil (ses angles, du plus probable au moins probable), puis le
        # plus probable des coupons qui atteignent la cote.
        coupons = [
            target_coupon(
                await best_angles(session, prof, start, end, now, filters=filters),
                target_odds,
                size,
            )
            for prof in PROFILES.values()
        ]
        reached = [c for c in coupons if c]
        # La cote la plus proche de la cible (critère indépendant de l'avis du moteur).
        chosen = min(reached, key=lambda c: (summarize(c)[0], len(c))) if reached else []
        chosen.sort(key=lambda pk: (pk.match.kickoff_at, pk.match.id))
        others: list[Pick] = []
        if not chosen:
            out["message"] = (
                f"Impossible d'atteindre une cote de {target_odds} avec {size} sélections au plus "
                f"sur « {period_label.lower()} » : élargis la période, ajoute des championnats, "
                "autorise plus de sélections ou vise une cote plus basse."
            )
            return out
    else:
        prof = PROFILES[profile]
        picks = await best_angles(session, prof, start, end, now, filters=filters)
        chosen, others = picks[:size], picks[size : size + ALTERNATIVES]
        if len(chosen) < size:
            out["message"] = (
                f"Seulement {len(chosen)} match(s) avec une sélection « {prof.label.lower()} » et "
                f"une vraie cote pour « {period_label.lower()} » : élargis la période, change de "
                "profil ou réduis le nombre de sélections."
            )
            if not chosen:
                return out
    total, probability = summarize(chosen)
    out["coupon"] = {
        "selections": [
            _selection_out(pk, await match_analysis(session, pk.match.id)) for pk in chosen
        ],
        "total_odds": total,
        "probability": round(probability, 6),
        "implied_probability": round(float(1 / total), 6),
        # « 1 chance sur N », selon le moteur.
        "one_in": max(1, round(1 / probability)) if probability > 0 else None,
    }
    out["alternatives"] = [
        _selection_out(pk, await match_analysis(session, pk.match.id)) for pk in others
    ]
    return out


# ------------------------------------------------------------ coupons du jour

# Coupons publics générés chaque matin pour la journée (après cotes et prédictions).
# Coupons du jour : nombre de sélections au plus, et cote totale minimale (None : aucune).
# Équilibré et Audacieux visent au moins 2,00 (décision du 07/10/2026 ; rejoué sur la saison
# 2025-26 : Équilibré 2,6 sélections, cote médiane 2,42, 40 % annoncé, 38 % réalisé) ;
# Sûr garde sa règle (vers 70 % de réussite, cote 1,4 à 1,8).
DAILY_RULES: dict[str, tuple[int, Decimal | None]] = {
    "sur": (3, None),
    "equilibre": (3, Decimal("2.00")),
    "audacieux": (3, Decimal("2.00")),
}
HISTORY_LIMIT = 60


async def create_daily(session: AsyncSession, now: datetime | None = None) -> dict[str, Any]:
    """Enregistre le coupon du jour de chaque profil, **avant** les matchs (une fois par jour)."""
    now = now or datetime.now(UTC)
    day = now.date()
    out: dict[str, Any] = {}
    for profile, (size, min_odds) in DAILY_RULES.items():
        exists = await session.scalar(
            select(SmartCoupon.id).where(SmartCoupon.day == day, SmartCoupon.profile == profile)
        )
        if exists is not None:
            out[profile] = "déjà créé"
            continue
        start, end = period_window("today", now)
        ranked = await best_angles(session, PROFILES[profile], start, end, now)
        # Sélections les plus probables, ajoutées jusqu'à la cote minimale (sinon pas de coupon).
        picks = ranked[:size] if min_odds is None else target_coupon(ranked, min_odds, size)
        if not picks:
            out[profile] = "aucune sélection"
            continue
        total, probability = summarize(picks)
        session.add(
            SmartCoupon(
                day=day,
                profile=profile,
                size=len(picks),
                selections=[_stored(pk) for pk in picks],
                total_odds=total,
                probability=probability,
                status="pending",
            )
        )
        out[profile] = f"{len(picks)} sélection(s), cote {total}"
    await session.commit()
    return out


def _stored(pick: Pick) -> dict[str, Any]:
    return {
        "match_id": pick.match.id,
        "home": pick.home,
        "away": pick.away,
        "competition": pick.competition,
        "kickoff_at": pick.match.kickoff_at.isoformat() if pick.match.kickoff_at else None,
        "market": pick.offer.market,
        "line": pick.offer.line,
        "selection": pick.offer.selection,
        "label": pick.offer.label,
        "odds": str(pick.offer.odds),
        "bookmaker": pick.offer.bookmaker,
        "model_probability": round(pick.probability, 4),
        "result": "pending",
    }


async def settle_pending(session: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """Règle les coupons du jour dont tous les matchs sont connus (mêmes règles que les paris)."""
    now = now or datetime.now(UTC)
    settled = {"won": 0, "lost": 0, "partial": 0, "void": 0}
    coupons = await session.scalars(select(SmartCoupon).where(SmartCoupon.status == "pending"))
    for coupon in coupons.all():
        grades, selections = [], []
        for s in coupon.selections:
            probe = BetSelection(
                match_id=s["match_id"],
                market=s["market"],
                line=s["line"],
                selection=s["selection"],
                odds=Decimal(s["odds"]),
            )
            grade = await settlement.grade_selection(session, probe, now)
            selections.append({**s, "result": grade.result if grade else "pending"})
            if grade is not None:
                grades.append(grade)
        coupon.selections = selections
        # Perdu dès qu'une sélection est perdue, sans attendre les autres matchs.
        if any(g.result == "loss" for g in grades) or len(grades) == len(selections):
            outcome, _ = settlement.bet_outcome(100, grades)
            # Lignes asiatiques : « partial » = gagné en partie (demi-gain ou demi-perte).
            coupon.status = "void" if outcome == "push" else outcome
            coupon.settled_at = now
            settled[coupon.status] += 1
    await session.commit()
    return settled


def _profile_record(coupons: Sequence[SmartCoupon]) -> dict[str, Any]:
    """Bilan par profil : un coupon Sûr et un Audacieux n'ont pas la même chance, ils ne
    s'additionnent pas. Annoncé (moyenne des probabilités) contre observé (taux réel)."""
    out: dict[str, Any] = {}
    for profile, prof in PROFILES.items():
        done = [
            c for c in coupons if c.profile == profile and c.status in ("won", "lost", "partial")
        ]
        n = len(done)
        won = sum(c.status == "won" for c in done)
        out[profile] = {
            "label": prof.label,
            "settled": n,
            "won": won,
            "announced": round(sum(c.probability for c in done) / n, 4) if n else None,
            "observed": round(won / n, 4) if n else None,
        }
    return out


async def history(
    session: AsyncSession,
    limit: int = HISTORY_LIMIT,
    *,
    offset: int = 0,
    premium: bool = True,
) -> dict[str, Any]:
    """Historique public : chaque coupon du jour, gagné ou perdu, et le bilan par profil.

    Page par page (``offset``) : rien n'est retiré de la liste, les plus anciens sont
    seulement plus bas (``has_more``). Sans Premium, un coupon pas encore réglé est montré
    sans ses sélections (``locked``) ; réglé, il est public en entier : la preuve que rien
    n'est trié après coup."""
    rows = (
        await session.scalars(
            select(SmartCoupon)
            .order_by(SmartCoupon.day.desc(), SmartCoupon.id)
            .offset(offset)
            .limit(limit + 1)
        )
    ).all()
    done = (
        await session.scalars(
            select(SmartCoupon).where(SmartCoupon.status.in_(("won", "lost", "partial")))
        )
    ).all()
    return {
        "stats": _profile_record(done),
        "has_more": len(rows) > limit,
        "coupons": [
            {
                "id": c.id,
                "day": c.day,
                "profile": c.profile,
                "profile_label": PROFILES[c.profile].label,
                "selections": [] if _locked(c, premium) else c.selections,
                "selection_count": len(c.selections),
                "locked": _locked(c, premium),
                "total_odds": c.total_odds,
                "probability": round(c.probability, 4),
                "status": c.status,
                "settled_at": c.settled_at,
            }
            for c in rows[:limit]
        ],
    }


# Bookmakers dont l'administrateur peut saisir le code de réservation d'un coupon.
BOOKING_BOOKMAKERS = {"1xbet": "1xBet"}
BOOKING_CODE = re.compile(r"^[A-Z0-9]{4,16}$")
WON_RESULTS = frozenset({"win", "half_win"})


def _live_state(selection: dict[str, Any], match: Match | None) -> dict[str, Any]:
    """État d'une sélection pour l'affichage : réglée, en cours (minute, score) ou à venir."""
    result = selection.get("result", "pending")
    out: dict[str, Any] = {"state": "settled" if result != "pending" else "upcoming"}
    if match is None:
        return out
    if match.status is MatchStatus.FINISHED:
        out["score"] = [match.home_goals, match.away_goals]
        if result == "pending":
            out["state"] = "finished"  # résultat connu, règlement au prochain passage
    elif match.api_status in LIVE_STATUSES:
        out["state"] = "live"
        out["minute"] = match.live_minute
        if match.live_home_goals is not None:
            out["score"] = [match.live_home_goals, match.live_away_goals]
    return out


def _locked(coupon: SmartCoupon, premium: bool) -> bool:
    """Coupons du jour réservés à Premium tant qu'ils ne sont pas réglés (sélections et code)."""
    return not premium and coupon.status == "pending"


def _coupon_out(
    coupon: SmartCoupon, matches: dict[int, Match], *, premium: bool = True
) -> dict[str, Any]:
    locked = _locked(coupon, premium)
    selections = [
        {**sel, **_live_state(sel, matches.get(sel["match_id"]))} for sel in coupon.selections
    ]
    validated = sum(sel.get("result") in WON_RESULTS for sel in selections)
    started = any(sel["state"] != "upcoming" for sel in selections)
    # Affichage : réglé (gagné, perdu…), en cours dès qu'un match a commencé, sinon à venir.
    display = coupon.status if coupon.status != "pending" else ("live" if started else "upcoming")
    kickoffs = [sel["kickoff_at"] for sel in selections if sel.get("kickoff_at")]
    return {
        "id": coupon.id,
        "day": coupon.day,
        "profile": coupon.profile,
        "profile_label": PROFILES[coupon.profile].label,
        # Sans Premium : profil, cote, chance et avancement ; ni sélections ni code.
        "locked": locked,
        "selection_count": len(selections),
        "selections": [] if locked else selections,
        "total_odds": coupon.total_odds,
        "probability": round(coupon.probability, 4),
        "status": coupon.status,
        "display_status": display,
        "validated": validated,
        "first_kickoff": min(kickoffs) if kickoffs else None,
        "booking_codes": []
        if locked
        else [
            {"bookmaker": key, "label": BOOKING_BOOKMAKERS.get(key, key), "code": code}
            for key, code in sorted(coupon.booking_codes.items())
        ],
        "settled_at": coupon.settled_at,
    }


def _record(coupons: Sequence[SmartCoupon]) -> dict[str, int]:
    done = [c for c in coupons if c.status in ("won", "lost", "partial")]
    return {"settled": len(done), "won": sum(c.status == "won" for c in done)}


async def day_coupons(
    session: AsyncSession,
    day: date | None = None,
    now: datetime | None = None,
    *,
    premium: bool = True,
) -> dict[str, Any]:
    """Coupons du jour d'une date (aujourd'hui par défaut), avec l'état en direct de chaque
    sélection, les codes de réservation, et le bilan de la veille et des 30 derniers jours."""
    today = (now or datetime.now(UTC)).date()
    day = day or today
    coupons = (
        await session.scalars(
            select(SmartCoupon).where(SmartCoupon.day == day).order_by(SmartCoupon.id)
        )
    ).all()
    ids = {sel["match_id"] for c in coupons for sel in c.selections}
    matches = (
        {m.id: m for m in (await session.scalars(select(Match).where(Match.id.in_(ids)))).all()}
        if ids
        else {}
    )
    recent = (
        await session.scalars(
            select(SmartCoupon).where(
                SmartCoupon.day >= today - timedelta(days=30), SmartCoupon.day < today
            )
        )
    ).all()
    yesterday = today - timedelta(days=1)
    order = list(PROFILES)
    return {
        "day": day,
        "coupons": sorted(
            (_coupon_out(c, matches, premium=premium) for c in coupons),
            key=lambda c: order.index(c["profile"]),
        ),
        "summary": {
            "yesterday": _record([c for c in recent if c.day == yesterday]),
            "last_30_days": _record(recent),
            "last_30_days_by_profile": _profile_record(recent),
        },
    }


async def set_booking_code(
    session: AsyncSession, coupon_id: int, bookmaker: str, code: str
) -> dict[str, Any]:
    """Enregistre (ou retire, code vide) le code de réservation d'un coupon du jour."""
    if bookmaker not in BOOKING_BOOKMAKERS:
        raise AppError(f"bookmaker inconnu : {bookmaker} ({', '.join(BOOKING_BOOKMAKERS)})")
    coupon = await session.get(SmartCoupon, coupon_id)
    if coupon is None:
        raise NotFoundError("coupon du jour introuvable")
    code = re.sub(r"\s+", "", code).upper()
    if code and not BOOKING_CODE.match(code):
        raise AppError("code invalide : 4 à 16 lettres ou chiffres, sans espace ni symbole")
    codes = dict(coupon.booking_codes)
    if code:
        codes[bookmaker] = code
    else:
        codes.pop(bookmaker, None)
    coupon.booking_codes = codes
    await session.commit()
    return await day_coupons(session, coupon.day)


async def notify_ready(session: AsyncSession, now: datetime | None = None) -> int:
    """Notification « coupons du jour disponibles », une seule fois par jour, dès que chaque
    coupon du jour a son code 1xBet ; aux comptes Premium actifs qui ne l'ont pas désactivée
    (un compte gratuit ne peut pas ouvrir les coupons du jour).

    Enregistrée dans la transaction ; l'appelant la diffuse ensuite (``publish_pending``).
    Renvoie le nombre de comptes prévenus.
    """
    now = now or datetime.now(UTC)
    coupons = (
        await session.scalars(
            select(SmartCoupon).where(SmartCoupon.day == now.date()).order_by(SmartCoupon.id)
        )
    ).all()
    if (
        not coupons
        or any(c.notified_at is not None for c in coupons)
        or not all("1xbet" in c.booking_codes for c in coupons)
    ):
        return 0
    order = list(PROFILES)
    parts = [
        f"{PROFILES[c.profile].label} {str(c.total_odds).replace('.', ',')}"
        for c in sorted(coupons, key=lambda c: order.index(c.profile))
    ]
    body = " · ".join(parts) + " : chance estimée et code 1xBet à copier dans l'application."
    users = (
        await session.scalars(
            select(User.id).where(
                User.is_active, User.daily_coupons_notifications, User.premium_until > now
            )
        )
    ).all()
    for user_id in users:
        notifications.add(
            session,
            user_id,
            "daily_coupons",
            "Coupons du jour disponibles",
            body,
            {"screen": "daily_coupons", "day": now.date().isoformat()},
        )
    for c in coupons:
        c.notified_at = now
    await session.commit()
    return len(users)
