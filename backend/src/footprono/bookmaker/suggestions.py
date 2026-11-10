"""Suggestions pour un palier de montante (validées le 30/09/2026, docs/DESIGN.md).

Les 3 paris (simple, ou combiné de 2 à 3 matchs différents) dont la cote
totale réelle est dans la plage. Pour chacun : probabilité du moteur et
probabilité déduite de la cote (1 / cote), côte à côte. Rien n'est joué sans
validation de l'utilisateur.

Classement (06/11/2026) : la cote la plus basse de la plage d'abord (le plus
probable selon le bookmaker), puis le moins de sélections (moins de marges
cumulées), puis le match le plus proche. Avant : par probabilité du moteur.
Or, dans une plage de cote fixe, le plus probable selon le moteur est celui
où il contredit le plus la cote (essai réel : « Modèle 76 % » pour 63 % selon
la cote, trois fois sur trois), et la cote a le plus souvent raison dans ces
désaccords (docs/MOTEUR.md, Coupon « Grosse cote »).

Marchés : les mêmes règles que le Coupon intelligent (``rules.automatic``).
"""

import itertools
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.bookmaker import playable, service, smart_coupon
from footprono.bookmaker.odds_math import combined_odds
from footprono.bookmaker.rules import automatic
from footprono.bookmaker.smart_coupon import MIN_ODDS
from footprono.football.models import Match, MatchStatus

HORIZON = timedelta(days=3)
CLOSE_BEFORE_KICKOFF = timedelta(minutes=15)
POOL_PAIRS, POOL_TRIPLES = 60, 25


@dataclass(frozen=True)
class Candidate:
    match_id: int
    kickoff_at: datetime
    offer: service.Offer
    probability: float


async def _candidates(
    session: AsyncSession, high: Decimal, now: datetime, redis: Redis | None = None
) -> list[Candidate]:
    start, end = now + CLOSE_BEFORE_KICKOFF, now + HORIZON
    first = await smart_coupon.next_kickoff(session, start)
    if first is not None and first >= end:
        # Trêve : rien dans les 3 jours, on prend la prochaine journée.
        day = datetime(first.year, first.month, first.day, tzinfo=UTC)
        end = day + timedelta(days=smart_coupon.NEXT_ROUND_DAYS)
    matches = (
        await session.scalars(
            select(Match).where(
                Match.status == MatchStatus.SCHEDULED,
                Match.kickoff_at.between(start, end),
                or_(Match.api_status.is_(None), Match.api_status.in_(("NS", "TBD"))),
            )
        )
    ).all()
    out = []
    all_offers, all_probs = await playable.load(session, [m.id for m in matches], now, redis)
    for match in matches:
        if match.kickoff_at is None:  # jamais : la période est choisie sur l'heure du match
            continue
        offers, probs = all_offers.get(match.id, {}), all_probs.get(match.id, {})
        for k, offer in offers.items():
            p = probs.get(k)
            # Ni cote trop basse (1,02 vu le 10/11/2026), ni cote que la source n'a pas
            # mise à jour depuis plus de 2 jours.
            if p is None or not automatic(offer.market) or not MIN_ODDS <= offer.odds <= high:
                continue
            if not service.fresh(offer, now):
                continue
            out.append(Candidate(match.id, match.kickoff_at, offer, p))
    return out


def _describe(combo: tuple[Candidate, ...]) -> dict[str, Any]:
    probability = 1.0
    for c in combo:
        probability *= c.probability
    total = combined_odds(c.offer.odds for c in combo)
    implied = float(1 / total)
    return {
        "selections": [
            {
                "match_id": c.match_id,
                "market": c.offer.market,
                "line": c.offer.line,
                "selection": c.offer.selection,
                "odds": c.offer.odds,
                "bookmaker": c.offer.bookmaker,
                "label": c.offer.label,
                "model_probability": round(c.probability, 4),
            }
            for c in combo
        ],
        "total_odds": total,
        "model_probability": round(probability, 4),
        # Affichée à côté, sans « bon plan » : face au marché, le moteur ne
        # gagne pas (log loss et rendement aux vraies cotes, docs/MOTEUR.md).
        "implied_probability": round(implied, 4),
        # Le moteur juge ce pari moins probable que la cote (marge comprise) : dit au joueur
        # (essai du 07/11/2026 : 57 % selon le moteur, 65 % selon la cote, sans explication).
        "engine_below_odds": probability < implied,
    }


async def suggest(
    session: AsyncSession,
    low: Decimal,
    high: Decimal,
    *,
    now: datetime | None = None,
    limit: int = 3,
    redis: Redis | None = None,
    exclude_matches: frozenset[int] = frozenset(),
) -> list[dict[str, Any]]:
    """``exclude_matches`` : matchs déjà pris par les autres montantes du joueur."""
    now = now or datetime.now(UTC)
    pool = [
        c for c in await _candidates(session, high, now, redis) if c.match_id not in exclude_matches
    ]
    return rank(pool, low, high, limit)


def rank(
    candidates: list[Candidate], low: Decimal, high: Decimal, limit: int = 3
) -> list[dict[str, Any]]:
    """Les ``limit`` paris de la plage : cote la plus basse, moins de sélections, plus proche."""
    # Ordre neutre (le plus proche d'abord) : jamais l'avis du moteur pour choisir.
    pool = sorted(candidates, key=lambda c: (c.kickoff_at, c.match_id))
    found: list[tuple[tuple[Decimal, int, datetime], tuple[Candidate, ...]]] = []

    def consider(combo: tuple[Candidate, ...]) -> None:
        if len({c.match_id for c in combo}) != len(combo):
            return  # jamais deux sélections du même match (elles sont liées)
        total = combined_odds(c.offer.odds for c in combo)
        if low <= total <= high:
            # Cote la plus basse, moins de sélections, match le plus proche.
            found.append(((total, len(combo), min(c.kickoff_at for c in combo)), combo))

    def legs(n: int) -> list[Candidate]:
        """Sélections dont la cote permet d'atteindre la plage à ``n`` (racine n-ième)."""
        lo, hi = float(low) ** (1 / n) / 1.25, float(high) ** (1 / n) * 1.25
        return [c for c in pool if lo <= float(c.offer.odds) <= hi]

    for c in pool:
        consider((c,))
    for pair in itertools.combinations(legs(2)[:POOL_PAIRS], 2):
        consider(pair)
    for triple in itertools.combinations(legs(3)[:POOL_TRIPLES], 3):
        consider(triple)
    found.sort(key=lambda t: t[0])
    # Le choix des suggestions ne regarde jamais l'avis du moteur face à la cote (préférer
    # les paris où il est plus confiant que le bookmaker, c'est choisir là où il se trompe le
    # plus, 03/10/2026). Seul l'affichage change : un désaccord est montré en dernier.
    out = [_describe(combo) for _, combo in found[:limit]]
    return sorted(out, key=lambda d: bool(d["engine_below_odds"]))
