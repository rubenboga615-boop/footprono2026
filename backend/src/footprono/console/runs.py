"""Exécutions des tâches planifiées, pour la frise des dernières 24 h de la console.

Chaque tâche du worker enregistre son passage dans Redis (liste par tâche, les
plus récentes en tête, ``KEEP`` au plus) : début, durée, statut et, en cas d'échec,
la cause (message de l'erreur, sans identifiants). Sans Redis, rien n'est enregistré
et la tâche s'exécute normalement.
"""

import functools
import json
import logging
import re
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
    "premium_reminders": "Rappels Premium",
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


# Identifiants d'une adresse (« postgresql://nom:motdepasse@hôte ») : jamais affichés.
_CREDENTIALS = re.compile(r"://[^/@\s]+@")


def error_text(error: BaseException) -> str:
    """Cause d'un échec, lisible dans la console et la notification (300 caractères)."""
    text = f"{type(error).__name__} : {error}".strip().rstrip(":").strip()
    return _CREDENTIALS.sub("://***@", text)[:300]


def _failure(result: Any) -> str | None:
    """Échec rendu par la tâche elle-même (source indisponible…) : sa raison."""
    if isinstance(result, dict) and _status(result) == "error":
        reason = result.get("reason") or result.get("error") or "source indisponible"
        return _CREDENTIALS.sub("://***@", str(reason))[:300]
    return None


def tracked(name: str) -> Callable[[F], F]:
    """Enregistre chaque exécution de la tâche (statut, durée)."""

    def decorate(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            started = time.time()
            status = "error"
            error: str | None = None
            try:
                result = func(*args, **kwargs)
                status = _status(result)
                error = _failure(result)
                return result
            except BaseException as exc:
                error = error_text(exc)
                raise
            finally:
                entry: dict[str, Any] = {
                    "at": started, "s": round(time.time() - started, 1), "st": status,
                }  # fmt: skip
                if error is not None:
                    entry["err"] = error
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
                    "error": entry.get("err"),
                }
            )
        out.append({"task": name, "label": label, "runs": runs})
    return out
