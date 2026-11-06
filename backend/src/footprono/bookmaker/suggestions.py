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

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.bookmaker import service, smart_coupon
from footprono.bookmaker.rules import automatic
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


async def _candidates(session: AsyncSession, high: Decimal, now: datetime) -> list[Candidate]:
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
    ids = [m.id for m in matches]
    all_offers, all_probs = await service.cached_offers_and_probabilities(session, ids, now)
    for match in matches:
        if match.kickoff_at is None:  # jamais : la période est choisie sur l'heure du match
            continue
        offers, probs = all_offers.get(match.id, {}), all_probs.get(match.id, {})
        for k, offer in offers.items():
            p = probs.get(k)
            if p is None or not automatic(offer.market) or not 1 < offer.odds <= high:
                continue
            out.append(Candidate(match.id, match.kickoff_at, offer, p))
    return out


def _describe(combo: tuple[Candidate, ...]) -> dict[str, Any]:
    total = Decimal(1)
    probability = 1.0
    for c in combo:
        total *= c.offer.odds
        probability *= c.probability
    total = total.quantize(Decimal("0.001"))
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
    }


async def suggest(
    session: AsyncSession,
    low: Decimal,
    high: Decimal,
    *,
    now: datetime | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    return rank(await _candidates(session, high, now), low, high, limit)


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
        total = Decimal(1)
        for c in combo:
            total *= c.offer.odds
        total = total.quantize(Decimal("0.001"))
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
    return [_describe(combo) for _, combo in found[:limit]]
