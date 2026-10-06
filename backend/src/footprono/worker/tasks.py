"""Tâches de fond."""

import asyncio
import logging
from typing import Any

from celery.signals import worker_ready
from sqlalchemy.ext.asyncio import AsyncEngine

from footprono import __version__, alerts
from footprono.accounts.reminders import send_premium_reminders
from footprono.bookmaker import settlement, smart_coupon
from footprono.cache.redis import create_redis
from footprono.console import jobs as console_jobs
from footprono.console.runs import tracked
from footprono.core.config import Settings, get_settings
from footprono.core.errors import AppError
from footprono.db.session import create_engine, create_session_factory
from footprono.football.models import DataSource
from footprono.ingestion import live
from footprono.ingestion.reference import COMPETITIONS, current_season
from footprono.ingestion.service import IngestionRequest, run_ingestion
from footprono.notifications import service as notifications
from footprono.notifications.push import sender_or_none as push_sender_or_none
from footprono.payments import service as payment_service
from footprono.predictions import service as prediction_service
from footprono.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _settle(engine: AsyncEngine, settings: Settings) -> dict[str, Any]:
    """Règle les paris ; notifications en direct (Redis) et sur téléphone (Firebase)."""
    redis = create_redis(settings)
    push = push_sender_or_none(settings)
    try:
        async with create_session_factory(engine)() as session:
            report = await settlement.settle_bets(session, redis=redis, push=push)
        async with create_session_factory(engine)() as session:
            report["smart_coupons"] = await smart_coupon.settle_pending(session)
        # Tous les codes 1xBet du jour saisis : « coupons du jour disponibles » (une fois).
        async with create_session_factory(engine)() as session:
            report["daily_coupons_notified"] = await smart_coupon.notify_ready(session)
            await notifications.publish_pending(session, redis, push)
        return report
    finally:
        await redis.aclose()
        if push is not None:
            await push.aclose()


@celery_app.task(name="footprono.ping")
def ping() -> dict[str, str]:
    """Tâche de contrôle : prouve qu'un worker consomme bien la file."""
    return {"status": "ok", "version": __version__}


@celery_app.task(name="footprono.ingest_current_season")
@tracked("ingest_current_season")
def ingest_current_season() -> dict[str, Any]:
    """Télécharge la saison en cours (football-data, Understat, API-Football), puis contrôle.

    Une source indisponible est consignée dans le rapport (statut ``partial``) ;
    aucune donnée de remplacement n'est produite.
    """
    return asyncio.run(_ingest_current_season())


async def _ingest_current_season() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        # Saison en cours de chaque championnat (année civile en Norvège et en Suède) :
        # une demande par saison.
        by_season: dict[int, list[str]] = {}
        for c in COMPETITIONS:
            by_season.setdefault(current_season(c), []).append(c.code)
        report = await run_ingestion(
            create_session_factory(engine),
            settings,
            [
                IngestionRequest(source, codes, [season])
                for season, codes in sorted(by_season.items())
                for source in (
                    DataSource.FOOTBALL_DATA,
                    DataSource.UNDERSTAT,
                    DataSource.API_FOOTBALL,
                )
            ],
        )
        # Scores confirmés par football-data : paris récents revus si un score a changé.
        bets = await _settle(engine, settings)
    finally:
        await engine.dispose()
    failed = [f for f in report["files"] if f["status"] in ("failed", "rejected")]
    return {
        "bets": bets,
        "run_id": report["run_id"],
        "status": report["status"],
        # Cause montrée dans la console et dans l'alerte (trois fichiers au plus).
        "reason": "; ".join(
            f"{f['competition']} {f['season']} : {f.get('error', '')}" for f in failed[:3]
        )
        or None,
        "files": {f"{f['source']}:{f['competition']}": f["status"] for f in report["files"]},
        "quality_errors": report["quality"]["errors"],
    }


@celery_app.task(name="footprono.collect_odds")
@tracked("collect_odds")
def collect_odds() -> dict[str, Any]:
    """Cotes des matchs à venir, puis blessés et suspendus du jour et du lendemain."""
    return asyncio.run(_collect_odds())


async def _collect_odds() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            report = await live.collect_odds(session, settings)
        async with create_session_factory(engine)() as session:
            injuries = await live.collect_injuries(session, settings)
    finally:
        await engine.dispose()
    # Le calendrier vient d'être synchronisé : nouveaux matchs prédits sans attendre.
    predict_if_needed.delay()
    return {
        "odds": {k: v for k, v in report.items() if k != "unmapped_bets"},
        "injuries": injuries,
    }


@celery_app.task(name="footprono.daily_smart_coupons")
@tracked("daily_smart_coupons")
def daily_smart_coupons() -> dict[str, Any]:
    """Coupons du jour de chaque profil, enregistrés avant les matchs (historique public)."""
    return asyncio.run(_daily_smart_coupons())


async def _daily_smart_coupons() -> dict[str, Any]:
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            return await smart_coupon.create_daily(session)
    finally:
        await engine.dispose()


@celery_app.task(name="footprono.follow_live")
@tracked("follow_live")
def follow_live() -> dict[str, Any]:
    """Score en direct, puis résultat et statistiques dès la fin des matchs.

    Sans match en cours, ne fait aucune requête : planifiable toutes les 2 minutes.
    """
    return asyncio.run(_follow_live())


async def _follow_live() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            report = await live.follow_live(session, settings)
        # Règlement juste après : un pari est payé dès la fin de son match.
        report["bets"] = await _settle(engine, settings)
        return report
    finally:
        await engine.dispose()


@celery_app.task(name="footprono.predict_upcoming")
@tracked("predict")
def predict_upcoming() -> dict[str, Any]:
    """Prédit les matchs des 10 prochains jours et enregistre les prédictions."""
    return asyncio.run(_predict_upcoming())


async def _predict_upcoming(only_if_needed: bool = False) -> dict[str, Any]:
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            reason = await prediction_service.prediction_needed(session)
            if only_if_needed and reason is None:
                return {"status": "skipped", "reason": "prédictions à jour"}
            run = await prediction_service.predict_upcoming(session)
            report = {k: v for k, v in run.report.items() if k != "window"}
            return {"run_id": run.id, "status": run.status, "reason": reason, "report": report}
    finally:
        await engine.dispose()


@celery_app.task(name="footprono.predict_if_needed")
@tracked("predict")
def predict_if_needed() -> dict[str, Any]:
    """Prédit seulement si nécessaire (prédictions de plus de 12 h, ou nouveaux matchs).

    Lancée au démarrage du worker, toutes les heures et après chaque collecte des
    cotes et du calendrier : un serveur éteint aux heures fixes rattrape son retard.
    """
    return asyncio.run(_predict_upcoming(only_if_needed=True))


@celery_app.task(name="footprono.check_payments")
@tracked("check_payments")
def check_payments() -> dict[str, Any]:
    """Revérifie auprès du prestataire les paiements en attente (moins de 24 h)."""
    return asyncio.run(_check_payments())


async def _check_payments() -> dict[str, Any]:
    settings = get_settings()
    if settings.cinetpay_api_key is None and settings.paystack_secret_key is None:
        return {"status": "idle", "reason": "aucun prestataire de paiement configuré"}
    engine = create_engine(settings)
    redis = create_redis(settings)
    push = push_sender_or_none(settings)
    counts: dict[str, int] = {}
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            pending = await payment_service.pending_to_check(session)
        for tx in pending:
            async with factory() as session:
                try:
                    payment = await payment_service.confirm(session, settings, tx)
                except AppError as exc:
                    logger.warning("payment_check_failed", extra={"tx": tx, "error": exc.message})
                    counts["error"] = counts.get("error", 0) + 1
                    continue
                await notifications.publish_pending(session, redis, push)
                counts[payment.status] = counts.get(payment.status, 0) + 1
    finally:
        await redis.aclose()
        if push is not None:
            await push.aclose()
        await engine.dispose()
    return {"status": "ok", "checked": len(pending), **counts}


# Acquittée dès la réception : une action de la console (collecte de plusieurs heures)
# n'est jamais relancée d'elle-même après un redémarrage ; elle est marquée interrompue
# et l'administrateur décide (console/jobs.py).
@celery_app.task(name="footprono.run_admin_job", acks_late=False)
def run_admin_job(job_id: int) -> dict[str, Any]:
    """Exécute une action lancée depuis la console d'administration."""
    return asyncio.run(_run_admin_job(job_id))


async def _run_admin_job(job_id: int) -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        status = await console_jobs.run_job(create_session_factory(engine), settings, job_id)
    finally:
        await engine.dispose()
    return {"job_id": job_id, "status": status}


@worker_ready.connect
def _catch_up_on_start(sender: Any = None, **_: Any) -> None:
    # Téléphone éteint aux heures prévues : le retard est rattrapé au démarrage.
    # Seulement pour le worker de l'application (pas les workers de test).
    if getattr(sender, "app", None) is not celery_app:
        return
    predict_if_needed.apply_async(countdown=30)


@celery_app.task(name="footprono.premium_reminders")
@tracked("premium_reminders")
def premium_reminders() -> dict[str, Any]:
    """Rappels « ton Premium se termine dans 3 jours / demain »."""
    return asyncio.run(_premium_reminders())


async def _premium_reminders() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    redis = create_redis(settings)
    push = push_sender_or_none(settings)
    try:
        async with create_session_factory(engine)() as session:
            sent = await send_premium_reminders(session)
            await notifications.publish_pending(session, redis, push)
    finally:
        await redis.aclose()
        if push is not None:
            await push.aclose()
        await engine.dispose()
    return {"status": "ok", "sent": sent}


@celery_app.task(name="footprono.alerts_watchdog")
def alerts_watchdog() -> dict[str, Any]:
    """Toutes les 10 minutes : alertes de l'administrateur sur son téléphone (ntfy)."""
    return asyncio.run(_alerts_watchdog())


async def _alerts_watchdog() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    redis = create_redis(settings)
    try:
        async with create_session_factory(engine)() as session:
            return await alerts.watchdog(session, redis, settings)
    finally:
        await redis.aclose()
        await engine.dispose()
