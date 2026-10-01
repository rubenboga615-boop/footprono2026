"""Sondes de vie et de disponibilité.

- ``/health`` : le processus répond (liveness). Ne touche aucune dépendance.
- ``/ready``  : le service peut réellement traiter des requêtes (readiness).
  Vérifie la base et Redis ; renvoie 503 avec le détail si l'une échoue,
  au lieu de prétendre que tout va bien.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from footprono import __version__
from footprono.api.deps import EngineDep, RedisDep, SettingsDep
from footprono.cache import redis as redis_cache
from footprono.db import session as db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["santé"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    environment: str


class CheckResult(BaseModel):
    ok: bool
    error: str | None = None


class ReadinessResponse(BaseModel):
    status: Literal["ready", "unavailable"]
    checks: dict[str, CheckResult]


@router.get("/health", response_model=HealthResponse)
async def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, environment=settings.environment)


async def _run_check(
    name: str, check: Callable[[], Awaitable[None]], limit_seconds: float
) -> CheckResult:
    try:
        async with asyncio.timeout(limit_seconds):
            await check()
        return CheckResult(ok=True)
    except Exception as exc:
        logger.warning("readiness_check_failed", extra={"check": name, "error": repr(exc)})
        return CheckResult(ok=False, error=type(exc).__name__)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def ready(settings: SettingsDep, engine: EngineDep, redis: RedisDep) -> JSONResponse:
    timeout = settings.readiness_timeout_seconds
    database, cache = await asyncio.gather(
        _run_check("database", lambda: db.ping(engine), timeout),
        _run_check("redis", lambda: redis_cache.ping(redis), timeout),
    )
    checks = {"database": database, "redis": cache}
    all_ok = all(c.ok for c in checks.values())
    body = ReadinessResponse(status="ready" if all_ok else "unavailable", checks=checks)
    return JSONResponse(body.model_dump(), status_code=200 if all_ok else 503)
