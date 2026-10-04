"""Tableau de bord de la console : état du serveur, dernières tâches, choses à traiter.

Tout est lu en base ou mesuré sur la machine au moment de la demande ; un service
qui ne répond pas est affiché comme tel, jamais comme « en marche ».
"""

import asyncio
import shutil
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any

from celery import Celery
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono import __version__
from footprono.accounts.models import User
from footprono.bookmaker.smart_coupon import BOOKING_BOOKMAKERS
from footprono.bookmaker.smart_models import SmartCoupon
from footprono.console.jobs import list_jobs
from footprono.core.config import Settings
from footprono.football.models import BookmakerOdds, IngestionRun
from footprono.payments.models import Payment
from footprono.predictions.models import PredictionRun


@cache
def _control_app(broker_url: str) -> Celery:
    # Même file que les workers : n'importe quelle application Celery peut les appeler.
    return Celery("footprono-console", broker=broker_url)


def _ping_worker(broker_url: str) -> int:
    """Nombre de workers Celery qui répondent (environ 1 s d'attente au plus)."""
    app = _control_app(broker_url)
    try:
        with app.connection_for_write() as conn:
            conn.ensure_connection(max_retries=1, interval_start=0, timeout=1)
            return len(app.control.ping(timeout=1.0, connection=conn) or [])
    except Exception:  # file injoignable : aucun worker joignable
        return 0


def _run(run: Any) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


async def dashboard(session: AsyncSession, redis: Redis, settings: Settings) -> dict[str, Any]:
    now = datetime.now(UTC)
    try:
        redis_ok = bool(await redis.ping())
    except Exception:
        redis_ok = False
    workers = await asyncio.to_thread(_ping_worker, settings.broker_url) if redis_ok else 0

    ingestion = await session.scalar(
        select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(1)
    )
    prediction = await session.scalar(
        select(PredictionRun).order_by(PredictionRun.started_at.desc()).limit(1)
    )
    last_odds = await session.scalar(select(func.max(BookmakerOdds.fetched_at)))

    today = now.date()
    coupons = (await session.scalars(select(SmartCoupon).where(SmartCoupon.day == today))).all()
    missing_codes = [
        c.profile
        for c in coupons
        if any(b not in (c.booking_codes or {}) for b in BOOKING_BOOKMAKERS)
    ]
    pending_payments = await session.scalar(
        select(func.count())
        .select_from(Payment)
        .where(Payment.status == "pending", Payment.created_at > now - timedelta(days=1))
    )
    users = await session.scalar(select(func.count()).select_from(User))
    premium = await session.scalar(
        select(func.count()).select_from(User).where(User.premium_until > now)
    )

    disk_path = (
        settings.raw_data_dir if settings.raw_data_dir.exists() else settings.raw_data_dir.parent
    )
    try:
        usage = shutil.disk_usage(disk_path if disk_path.exists() else ".")
        disk = {"free_gb": round(usage.free / 1e9, 1), "total_gb": round(usage.total / 1e9, 1)}
    except OSError:
        disk = None

    quality = (ingestion.report or {}).get("quality") if ingestion is not None else None
    todo: list[dict[str, str]] = []
    if workers == 0:
        todo.append({"level": "error", "text": "aucun worker Celery ne répond : tâches à l'arrêt"})
    if not redis_ok:
        todo.append({"level": "error", "text": "Redis ne répond pas"})
    if missing_codes:
        todo.append(
            {
                "level": "warning",
                "text": "codes 1xBet à saisir pour les coupons du jour : "
                + ", ".join(missing_codes),
                "link": "codes",
            }
        )
    if quality and quality.get("errors"):
        todo.append(
            {
                "level": "warning",
                "text": f"{quality['errors']} erreur(s) de qualité à la dernière ingestion",
                "action": "quality",
            }
        )
    if pending_payments:
        todo.append(
            {"level": "info", "text": f"{pending_payments} paiement(s) en attente de confirmation"}
        )
    if disk is not None and disk["free_gb"] < 2:
        todo.append({"level": "warning", "text": f"plus que {disk['free_gb']} Go libres"})
    if last_odds is None or now - last_odds > timedelta(hours=7):
        todo.append(
            {
                "level": "warning",
                "text": "pas de relevé de cotes depuis plus de 7 h",
                "action": "collect_odds",
            }
        )

    return {
        "now": now,
        "version": __version__,
        "environment": settings.environment.value,
        "services": {"database": True, "redis": redis_ok, "workers": workers},
        "disk": disk,
        "last": {
            "ingestion": _run(ingestion),
            "prediction": _run(prediction),
            "odds_at": last_odds,
        },
        "quality": (
            {k: quality.get(k) for k in ("status", "errors", "warnings")} if quality else None
        ),
        "coupons_today": {"count": len(coupons), "missing_codes": missing_codes},
        "users": {"total": users or 0, "premium": premium or 0},
        "todo": todo,
        "jobs": await list_jobs(session, limit=8),
    }
