"""Tâches de fond."""

import asyncio
from typing import Any

from footprono import __version__
from footprono.core.config import get_settings
from footprono.db.session import create_engine, create_session_factory
from footprono.football.models import DataSource
from footprono.ingestion.quality import current_season_start
from footprono.ingestion.reference import COMPETITIONS
from footprono.ingestion.service import IngestionRequest, run_ingestion
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
    finally:
        await engine.dispose()
    return {
        "run_id": report["run_id"],
        "status": report["status"],
        "files": {f"{f['source']}:{f['competition']}": f["status"] for f in report["files"]},
        "quality_errors": report["quality"]["errors"],
    }
