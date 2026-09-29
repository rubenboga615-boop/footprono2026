"""Tâches de fond."""

from footprono import __version__
from footprono.worker.celery_app import celery_app


@celery_app.task(name="footprono.ping")
def ping() -> dict[str, str]:
    """Tâche de contrôle : prouve qu'un worker consomme bien la file."""
    return {"status": "ok", "version": __version__}
