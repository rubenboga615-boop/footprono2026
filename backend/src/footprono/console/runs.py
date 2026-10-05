"""Exécutions des tâches planifiées, pour la frise des dernières 24 h de la console.

Chaque tâche du worker enregistre son passage dans Redis (liste par tâche, les
plus récentes en tête, ``KEEP`` au plus) : début, durée, statut. Sans Redis, rien
n'est enregistré et la tâche s'exécute normalement.
"""

import functools
import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

import redis
from redis.asyncio import Redis

from footprono.core.config import get_settings

logger = logging.getLogger(__name__)
KEEP = 800  # « direct » toutes les 2 minutes : un peu plus d'une journée
PREFIX = "console:runs:"

# Tâches affichées, dans l'ordre de la frise.
TRACKED = {
    "follow_live": "Direct (2 min)",
    "collect_odds": "Cotes (3 h)",
    "ingest_current_season": "Ingestion du matin",
    "predict": "Pronostics",
    "daily_smart_coupons": "Coupons du jour",
    "check_payments": "Paiements (10 min)",
}

F = TypeVar("F", bound=Callable[..., Any])
_client: redis.Redis | None = None


def _redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(str(get_settings().redis_url), socket_timeout=2)
    return _client


def _status(result: Any) -> str:
    if isinstance(result, dict):
        status = str(result.get("status") or "ok")
        return {"partial": "warning", "unavailable": "error", "skipped": "idle"}.get(status, status)
    return "ok"


def tracked(name: str) -> Callable[[F], F]:
    """Enregistre chaque exécution de la tâche (statut, durée)."""

    def decorate(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            started = time.time()
            status = "error"
            try:
                result = func(*args, **kwargs)
                status = _status(result)
                return result
            finally:
                entry = {"at": started, "s": round(time.time() - started, 1), "st": status}
                try:
                    client = _redis()
                    client.lpush(PREFIX + name, json.dumps(entry))
                    client.ltrim(PREFIX + name, 0, KEEP - 1)
                except Exception:  # Redis absent : la tâche compte plus que la frise
                    logger.warning("console_run_not_recorded", extra={"task": name})

        return wrapper  # type: ignore[return-value]

    return decorate


async def recent_runs(client: Redis, hours: int = 24) -> list[dict[str, Any]]:
    """Exécutions des dernières ``hours`` heures, par tâche suivie."""
    since = (datetime.now(UTC) - timedelta(hours=hours)).timestamp()
    out = []
    for name, label in TRACKED.items():
        try:
            raw = await client.lrange(PREFIX + name, 0, KEEP - 1)  # type: ignore[misc]
        except Exception:
            raw = []
        runs = []
        for item in raw:
            entry = json.loads(item)
            if entry["at"] < since:
                break
            runs.append(
                {
                    "at": datetime.fromtimestamp(entry["at"], UTC),
                    "seconds": entry["s"],
                    "status": entry["st"],
                }
            )
        out.append({"task": name, "label": label, "runs": runs})
    return out
