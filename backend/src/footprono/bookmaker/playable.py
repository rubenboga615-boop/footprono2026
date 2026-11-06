"""Sélections jouables préparées à l'avance : cotes et probabilités du moteur, par match.

Lire les cotes de tous les matchs d'une période prenait 15 à 19 secondes sur le serveur
(essai réel du 06/11/2026, docs/AUDIT_UTILISATEUR_2026-11-06.md) : le Coupon intelligent,
les coupons du jour et les suggestions de montante frôlaient le délai de 20 secondes de
l'application. Ces données ne changent qu'à la collecte des cotes et au calcul des
pronostics : elles sont donc préparées juste après (``refresh``, worker) et lues toutes
prêtes (``load``).

Jamais de données fausses :
- l'empreinte des données (dernière cote enregistrée, dernier calcul de pronostics) est
  gardée avec elles ; si elle ne correspond plus à la base, ou si Redis ne répond pas,
  les données sont recalculées comme avant (plus lent, toujours juste) ;
- une cote trop ancienne (``service.ODDS_MAX_AGE``) est écartée à la lecture ;
- au moment de miser, la cote est de toute façon revérifiée en direct (``place_bet``).
"""

import json
import logging
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.bookmaker import service
from footprono.bookmaker.rules import automatic
from footprono.football.models import BookmakerOdds, Match, MatchStatus
from footprono.predictions.models import PredictionRun

logger = logging.getLogger(__name__)

KEY = "playable:v1"  # hash : identifiant du match -> {"offers": …, "probs": …}
STAMP_FIELD = "_stamp"  # empreinte des données dans le même hash
HORIZON = timedelta(days=15)  # au-delà de la plus longue période proposée (14 jours)
TTL = timedelta(days=2)

Offers = dict[int, dict[str, service.Offer]]
# Données préparées déjà décodées (par processus), valables pour une seule empreinte.
_decoded: dict[Any, Any] = {}
Probs = dict[int, dict[str, float]]


async def stamp(session: AsyncSession) -> str:
    """Empreinte des données : dernière cote enregistrée et dernier calcul de pronostics."""
    odds = await session.scalar(select(func.max(BookmakerOdds.id)))
    run = await session.scalar(select(func.max(PredictionRun.id)))
    return f"{odds or 0}:{run or 0}"


def _offer_out(o: service.Offer) -> dict[str, Any]:
    return {
        "market": o.market, "line": o.line, "selection": o.selection, "odds": str(o.odds),
        "bookmaker": o.bookmaker, "quote_id": o.quote_id, "fetched_at": o.fetched_at.isoformat(),
        "label": o.label,
        "source_updated_at": o.source_updated_at.isoformat() if o.source_updated_at else None,
        "checked_at": o.checked_at.isoformat() if o.checked_at else None,
    }  # fmt: skip


def _offer_in(d: dict[str, Any]) -> service.Offer:
    def when(v: str | None) -> datetime | None:
        return datetime.fromisoformat(v) if v else None

    return service.Offer(
        market=d["market"], line=d["line"], selection=d["selection"], odds=Decimal(d["odds"]),
        bookmaker=d["bookmaker"], quote_id=d["quote_id"],
        fetched_at=datetime.fromisoformat(d["fetched_at"]), label=d["label"],
        source_updated_at=when(d["source_updated_at"]), checked_at=when(d["checked_at"]),
    )  # fmt: skip


async def _compute(session: AsyncSession, ids: list[int], now: datetime) -> tuple[Offers, Probs]:
    return await service.match_offers(session, ids, now), await service.models_probabilities(
        session, ids
    )


async def _fallback(session: AsyncSession, ids: list[int], now: datetime) -> tuple[Offers, Probs]:
    """Matchs non préparés (ou données périmées) : cache de quelques minutes par processus
    (``service.cached_offers_and_probabilities``), sinon lecture en base."""
    return await service.cached_offers_and_probabilities(session, ids, now)


async def refresh(session: AsyncSession, redis: Redis, now: datetime | None = None) -> int:
    """Prépare les sélections de tous les matchs des 15 prochains jours ; renvoie leur nombre."""
    now = now or datetime.now(UTC)
    current = await stamp(session)
    ids = list(
        await session.scalars(
            select(Match.id).where(
                Match.status == MatchStatus.SCHEDULED,
                Match.kickoff_at >= now,
                Match.kickoff_at < now + HORIZON,
                or_(Match.api_status.is_(None), Match.api_status.in_(("NS", "TBD"))),
            )
        )
    )
    offers, probs = await _compute(session, ids, now)
    mapping = {}
    for i in ids:
        # Seulement les sélections utilisables (marché choisi automatiquement, probabilité du
        # moteur connue) : le reste (des centaines de clés par match) ralentissait la lecture.
        kept = {
            k: o
            for k, o in offers.get(i, {}).items()
            if automatic(o.market) and k in probs.get(i, {})
        }
        mapping[str(i)] = json.dumps(
            {
                "offers": {k: _offer_out(o) for k, o in kept.items()},
                "probs": {k: probs[i][k] for k in kept},
            }
        )
    mapping[STAMP_FIELD] = current
    async with redis.pipeline(transaction=True) as pipe:
        pipe.delete(KEY)
        pipe.hset(KEY, mapping=mapping)
        pipe.expire(KEY, int(TTL.total_seconds()))
        await pipe.execute()
    return len(ids)


async def load(
    session: AsyncSession, ids: list[int], now: datetime, redis: Redis | None = None
) -> tuple[Offers, Probs]:
    """Cotes jouables et probabilités du moteur de ces matchs : préparées si elles sont à
    jour, sinon calculées (les matchs absents des données préparées aussi). Préparées, elles
    ne contiennent que les marchés choisis automatiquement (Coupon intelligent, suggestions)."""
    if not ids:
        return {}, {}
    raw: list[str | None] = []
    current = ""
    if redis is not None:
        try:
            values: list[str | None] = await cast(
                Awaitable[list[str | None]], redis.hmget(KEY, [STAMP_FIELD, *map(str, ids)])
            )
            current = await stamp(session)
            if values[0] == current:
                raw = values[1:]
        except RedisError as exc:  # Redis indisponible : calcul direct, jamais d'erreur
            logger.warning("playable_cache_unavailable", extra={"error": str(exc)})
    offers: Offers = {}
    probs: Probs = {}
    missing = []
    if raw and _decoded.get("stamp") != current:
        _decoded.clear()
        _decoded["stamp"] = current
    for i, value in zip(ids, raw or [None] * len(ids), strict=True):
        if value is None:
            missing.append(i)
            continue
        if i not in _decoded:
            data = json.loads(value)
            _decoded[i] = ({k: _offer_in(d) for k, d in data["offers"].items()}, data["probs"])
        all_offers, match_probs = _decoded[i]
        kept = {
            k: o
            for k, o in all_offers.items()
            if o.checked_at is None or now - o.checked_at <= service.ODDS_MAX_AGE
        }
        if kept:
            offers[i] = kept
        if match_probs:
            probs[i] = match_probs
    if missing:
        more_offers, more_probs = await _fallback(session, missing, now)
        offers.update(more_offers)
        probs.update(more_probs)
    return offers, probs
