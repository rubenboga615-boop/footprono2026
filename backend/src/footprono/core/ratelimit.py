"""Limitation des tentatives (connexion, inscription) : compteurs Redis par fenêtre.

Protège contre la recherche de mot de passe par essais successifs et contre la
création de comptes en masse. Redis indisponible : la requête passe (consigné),
l'application n'est pas bloquée par une panne du cache.
"""

import logging
import time

from fastapi import status
from redis.asyncio import Redis

from footprono.core.errors import AppError

logger = logging.getLogger(__name__)


class TooManyAttemptsError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "too_many_attempts"


def _key(scope: str, ident: str, window: int) -> str:
    return f"ratelimit:{scope}:{ident}:{int(time.time()) // window}"


async def check(redis: Redis, scope: str, ident: str, limit: int, window: int) -> None:
    """Refuse si ``limit`` tentatives ont déjà été comptées dans la fenêtre en cours."""
    try:
        count = int(await redis.get(_key(scope, ident, window)) or 0)
    except Exception:
        logger.warning("ratelimit_unavailable", extra={"scope": scope})
        return
    if count >= limit:
        minutes = max(1, window // 60)
        raise TooManyAttemptsError(
            f"trop de tentatives : réessaie dans {minutes} minutes au plus",
            details={"retry_after_seconds": window - int(time.time()) % window},
        )


async def hit(redis: Redis, scope: str, ident: str, window: int) -> None:
    """Compte une tentative (échouée pour la connexion, réussie pour l'inscription)."""
    key = _key(scope, ident, window)
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, window)
            await pipe.execute()
    except Exception:
        logger.warning("ratelimit_unavailable", extra={"scope": scope})
