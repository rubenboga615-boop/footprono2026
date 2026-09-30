"""Suggestions pour un palier de montante (validées le 30/09/2026, docs/DESIGN.md).

Les 3 paris (simple, ou combiné de 2 à 3 matchs différents) dont la cote
totale réelle est dans la plage, classés par probabilité du moteur. Pour
chacun : probabilité du moteur, probabilité déduite de la cote (1 / cote) et
l'écart ; un pari moins probable que sa cote ne le suppose est marqué
« déconseillé ». Rien n'est joué sans validation de l'utilisateur.

Exclus : marchés où le moteur ne fait pas mieux que les fréquences
(mi-temps la plus prolifique, docs/MOTEUR.md).
"""

import itertools
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.bookmaker import service
from footprono.football.models import Match, MatchStatus

EXCLUDED_MARKETS = frozenset({"HIGHEST_HALF"})
HORIZON = timedelta(days=3)
CLOSE_BEFORE_KICKOFF = timedelta(minutes=15)
POOL_PAIRS, POOL_TRIPLES = 60, 25


@dataclass(frozen=True)
class Candidate:
    match_id: int
    offer: service.Offer
    probability: float


async def _candidates(session: AsyncSession, high: Decimal, now: datetime) -> list[Candidate]:
    matches = (
        await session.scalars(
            select(Match).where(
                Match.status == MatchStatus.SCHEDULED,
                Match.kickoff_at.between(now + CLOSE_BEFORE_KICKOFF, now + HORIZON),
                or_(Match.api_status.is_(None), Match.api_status.in_(("NS", "TBD"))),
            )
        )
    ).all()
    out = []
    for match in matches:
        offers = await service.match_offer(session, match.id, now)
        probs = await service.model_probabilities(session, match.id)
        for k, offer in offers.items():
            p = probs.get(k)
            if p is None or offer.market in EXCLUDED_MARKETS or not 1 < offer.odds <= high:
                continue
            out.append(Candidate(match.id, offer, p))
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
        "implied_probability": round(implied, 4),
        "gap": round(probability - implied, 4),
        # Le moteur juge ce pari moins probable que ce que suppose sa cote.
        "advised": probability >= implied,
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
    pool = sorted(await _candidates(session, high, now), key=lambda c: -c.probability)
    found: list[tuple[float, tuple[Candidate, ...]]] = []

    def consider(combo: tuple[Candidate, ...]) -> None:
        if len({c.match_id for c in combo}) != len(combo):
            return  # jamais deux sélections du même match (elles sont liées)
        total = Decimal(1)
        probability = 1.0
        for c in combo:
            total *= c.offer.odds
            probability *= c.probability
        if low <= total.quantize(Decimal("0.001")) <= high:
            found.append((probability, combo))

    for c in pool:
        consider((c,))
    for pair in itertools.combinations(pool[:POOL_PAIRS], 2):
        consider(pair)
    for triple in itertools.combinations(pool[:POOL_TRIPLES], 3):
        consider(triple)
    found.sort(key=lambda t: -t[0])
    return [_describe(combo) for _, combo in found[:limit]]
