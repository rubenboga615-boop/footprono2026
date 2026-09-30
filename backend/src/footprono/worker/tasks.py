"""Tâches de fond."""

import asyncio
from typing import Any

from footprono import __version__
from footprono.bookmaker import settlement
from footprono.core.config import get_settings
from footprono.db.session import create_engine, create_session_factory
from footprono.football.models import DataSource
from footprono.ingestion import live
from footprono.ingestion.quality import current_season_start
from footprono.ingestion.reference import COMPETITIONS
from footprono.ingestion.service import IngestionRequest, run_ingestion
from footprono.predictions import service as prediction_service
from footprono.worker.celery_app import celery_app


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
        async with create_session_factory(engine)() as session:
            bets = await settlement.settle_bets(session)
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
        async with create_session_factory(engine)() as session:
            report["bets"] = await settlement.settle_bets(session)
        return report
    finally:
        await engine.dispose()


@celery_app.task(name="footprono.predict_upcoming")
def predict_upcoming() -> dict[str, Any]:
    """Prédit les matchs des 10 prochains jours et enregistre les prédictions."""
    return asyncio.run(_predict_upcoming())


async def _predict_upcoming() -> dict[str, Any]:
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            run = await prediction_service.predict_upcoming(session)
            return {"run_id": run.id, "status": run.status, "report": run.report}
    finally:
        await engine.dispose()
