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

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from footprono.bookmaker import service, settlement
from footprono.bookmaker.models import BetSelection
from footprono.bookmaker.rules import automatic
from footprono.bookmaker.smart_models import SmartCoupon
from footprono.core.errors import AppError
from footprono.football.analysis import match_analysis
from footprono.football.models import Competition, Match, MatchStatus, Season, Team


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
DAILY_SIZE = {"sur": 3, "equilibre": 2, "audacieux": 2}
HISTORY_LIMIT = 60


async def create_daily(session: AsyncSession, now: datetime | None = None) -> dict[str, Any]:
    """Enregistre le coupon du jour de chaque profil, **avant** les matchs (une fois par jour)."""
    now = now or datetime.now(UTC)
    day = now.date()
    out: dict[str, Any] = {}
    for profile, size in DAILY_SIZE.items():
        exists = await session.scalar(
            select(SmartCoupon.id).where(SmartCoupon.day == day, SmartCoupon.profile == profile)
        )
        if exists is not None:
            out[profile] = "déjà créé"
            continue
        start, end = period_window("today", now)
        picks = (await best_angles(session, PROFILES[profile], start, end, now))[:size]
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


async def history(session: AsyncSession, limit: int = HISTORY_LIMIT) -> dict[str, Any]:
    """Historique public : chaque coupon du jour, gagné ou perdu, et le bilan par profil."""
    rows = (
        await session.scalars(
            select(SmartCoupon).order_by(SmartCoupon.day.desc(), SmartCoupon.id).limit(limit)
        )
    ).all()
    stats: dict[str, Any] = {}
    for profile, prof in PROFILES.items():
        done = (
            await session.scalars(
                select(SmartCoupon).where(
                    SmartCoupon.profile == profile,
                    SmartCoupon.status.in_(("won", "lost", "partial")),
                )
            )
        ).all()
        n = len(done)
        stats[profile] = {
            "label": prof.label,
            "settled": n,
            "won": sum(c.status == "won" for c in done),
            # Moyenne des probabilités annoncées contre taux réel : l'annonce est-elle juste ?
            "announced": round(sum(c.probability for c in done) / n, 4) if n else None,
            "observed": round(sum(c.status == "won" for c in done) / n, 4) if n else None,
        }
    return {
        "stats": stats,
        "coupons": [
            {
                "id": c.id,
                "day": c.day,
                "profile": c.profile,
                "profile_label": PROFILES[c.profile].label,
                "selections": c.selections,
                "total_odds": c.total_odds,
                "probability": round(c.probability, 4),
                "status": c.status,
                "settled_at": c.settled_at,
            }
            for c in rows
        ],
    }
