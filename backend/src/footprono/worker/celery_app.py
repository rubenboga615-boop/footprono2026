"""Application Celery : tâches de fond et planification.

Lancement :
    celery -A footprono.worker.celery_app worker --loglevel=INFO
    celery -A footprono.worker.celery_app beat   --loglevel=INFO

Les tâches planifiées (ingestion, prédictions, règlement des paris,
notifications) seront ajoutées à ``beat_schedule`` dans les phases suivantes.
"""

from celery import Celery

from footprono.core.config import Settings, get_settings


def create_celery(settings: Settings | None = None) -> Celery:
    settings = settings or get_settings()
    app = Celery("footprono", broker=settings.broker_url, backend=settings.result_backend)
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        # Une tâche n'est acquittée qu'une fois terminée : si le worker meurt,
        # elle est redistribuée au lieu d'être perdue silencieusement.
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_track_started=True,
        result_expires=3600,
        broker_connection_retry_on_startup=True,
        beat_schedule={},
    )
    app.autodiscover_tasks(["footprono.worker"], related_name="tasks")
    return app


celery_app = create_celery()
