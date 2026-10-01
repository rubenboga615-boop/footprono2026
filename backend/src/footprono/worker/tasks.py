"""Tâches de fond."""

import asyncio
import logging
from typing import Any

from celery.signals import worker_ready
from sqlalchemy.ext.asyncio import AsyncEngine

from footprono import __version__
from footprono.bookmaker import settlement
from footprono.cache.redis import create_redis
from footprono.core.config import Settings, get_settings
from footprono.db.session import create_engine, create_session_factory
from footprono.football.models import DataSource
from footprono.ingestion import live
from footprono.ingestion.quality import current_season_start
from footprono.ingestion.reference import COMPETITIONS
from footprono.ingestion.service import IngestionRequest, run_ingestion
from footprono.notifications.push import FcmSender, PushConfigError
from footprono.predictions import service as prediction_service
from footprono.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _push_sender(settings: Settings) -> FcmSender | None:
    """Expéditeur Firebase, ou None (non configuré, ou clé inutilisable : consigné)."""
    try:
        return FcmSender.from_settings(settings)
    except PushConfigError as exc:
        logger.error("push_disabled", extra={"error": str(exc)})
        return None


async def _settle(engine: AsyncEngine, settings: Settings) -> dict[str, Any]:
    """Règle les paris ; notifications en direct (Redis) et sur téléphone (Firebase)."""
    redis = create_redis(settings)
    push = _push_sender(settings)
    try:
        async with create_session_factory(engine)() as session:
            return await settlement.settle_bets(session, redis=redis, push=push)
    finally:
        await redis.aclose()
        if push is not None:
            await push.aclose()


@celery_app.task(name="footprono.ping")
def ping() -> dict[str, str]:
    """Tâche de contrôle : prouve qu'un worker consomme bien la file."""
    return {"status": "ok", "version": __version__}


@celery_app.task(name="footprono.ingest_current_season")
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
        season = current_season_start()
        competitions = [c.code for c in COMPETITIONS]
        report = await run_ingestion(
            create_session_factory(engine),
            settings,
            [
                IngestionRequest(DataSource.FOOTBALL_DATA, competitions, [season]),
                IngestionRequest(DataSource.UNDERSTAT, competitions, [season]),
                IngestionRequest(DataSource.API_FOOTBALL, competitions, [season]),
            ],
        )
        # Scores confirmés par football-data : paris récents revus si un score a changé.
        bets = await _settle(engine, settings)
    finally:
        await engine.dispose()
    return {
        "bets": bets,
        "run_id": report["run_id"],
        "status": report["status"],
        "files": {f"{f['source']}:{f['competition']}": f["status"] for f in report["files"]},
        "quality_errors": report["quality"]["errors"],
    }


@celery_app.task(name="footprono.collect_odds")
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


@celery_app.task(name="footprono.follow_live")
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
def predict_if_needed() -> dict[str, Any]:
    """Prédit seulement si nécessaire (prédictions de plus de 12 h, ou nouveaux matchs).

    Lancée au démarrage du worker, toutes les heures et après chaque collecte des
    cotes et du calendrier : un serveur éteint aux heures fixes rattrape son retard.
    """
    return asyncio.run(_predict_upcoming(only_if_needed=True))


@worker_ready.connect
def _catch_up_on_start(sender: Any = None, **_: Any) -> None:
    # Téléphone éteint aux heures prévues : le retard est rattrapé au démarrage.
    # Seulement pour le worker de l'application (pas les workers de test).
    if getattr(sender, "app", None) is not celery_app:
        return
    predict_if_needed.apply_async(countdown=30)
