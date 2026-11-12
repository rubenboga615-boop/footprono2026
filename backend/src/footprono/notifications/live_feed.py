"""Relevés du direct poussés à l'application ouverte (retour du fondateur du 12/11/2026 :
il fallait actualiser sans arrêt pendant un match).

Après chaque passage du suivi en direct (``follow_live``), un message ``{"type": "live"}``
part sur le canal Redis commun ``LIVE_CHANNEL`` ; le WebSocket de chaque joueur connecté le
relaie (``api/v1/notifications.py``). Il porte, pour chaque match relevé : statut, minute,
score, buts et cartons rouges, et les chances du moment si elles sont publiées. Aucune
donnée personnelle ; aucune requête de plus vers API-Football.
"""

import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.football.live_view import live_summaries
from footprono.football.models import Match
from footprono.predictions import live_chances
from footprono.predictions.publication import live_published

logger = logging.getLogger(__name__)

LIVE_CHANNEL = "live"
# Dernier relevé poussé, gardé pour l'application sans WebSocket (invité, connexion coupée) :
# GET /api/v1/live/feed le relit sans toucher à la base (retour du 12/11/2026 : 158 requêtes
# en 8 minutes pour un joueur).
LAST_KEY = "live:last"
LAST_TTL = 600
# Chances envoyées dans le message : celles que la liste des matchs affiche.
# Lignes de buts 0,5 à 5,5 : « encore au moins un but » suit le score (12/11/2026).
SHOWN = ("1X2||home", "1X2||draw", "1X2||away", *(f"OU|{n}.5|over" for n in range(6)))


async def live_message(session: AsyncSession, match_ids: Sequence[int]) -> dict[str, Any]:
    ids = list(dict.fromkeys(match_ids))
    matches = list(await session.scalars(select(Match).where(Match.id.in_(ids)))) if ids else []
    summaries = await live_summaries(session, ids)
    chances = await live_chances.current(session, ids) if await live_published(session) else {}
    return {
        "type": "live",
        "at": datetime.now(UTC).isoformat(),
        "matches": [
            {
                "id": m.id,
                "status": m.status.value,
                "api_status": m.api_status,
                "minute": m.live_minute,
                "extra": m.live_extra,
                "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
                "updated_at": m.live_updated_at.isoformat() if m.live_updated_at else None,
                "home": m.live_home_goals if m.home_goals is None else m.home_goals,
                "away": m.live_away_goals if m.away_goals is None else m.away_goals,
                "goals": summaries.get(m.id, {}).get("goals", []),
                "reds": summaries.get(m.id, {}).get("reds", []),
                "chances": {
                    k: v
                    for k, v in (chances.get(m.id, {}).get("markets") or {}).items()
                    if k in SHOWN
                },
            }
            for m in matches
        ],
    }


async def publish_live(redis: Redis, session: AsyncSession, match_ids: Sequence[int]) -> int:
    """Pousse le relevé ; renvoie le nombre de matchs envoyés (0 : rien à envoyer)."""
    if not match_ids:
        return 0
    try:
        message = await live_message(session, match_ids)
        text = json.dumps(message, default=str)
        await redis.set(LAST_KEY, text, ex=LAST_TTL)
        await redis.publish(LIVE_CHANNEL, text)
    except Exception:  # le direct ne doit jamais faire échouer le suivi
        logger.warning("live_publish_failed", exc_info=True)
        return 0
    return len(message["matches"])


async def last_message(redis: Redis) -> dict[str, Any]:
    """Dernier relevé poussé (moins de 10 minutes), sinon un relevé vide."""
    text = await redis.get(LAST_KEY)
    if not text:
        return {"type": "live", "at": None, "matches": []}
    return dict(json.loads(text))
