"""Application Celery : tâches de fond et planification.

Lancement :
    celery -A footprono.worker.celery_app worker --loglevel=INFO
    celery -A footprono.worker.celery_app beat   --loglevel=INFO

Tâches planifiées (UTC) :
- ``footprono.ingest_current_season`` chaque matin à 06:15 (football-data met
  à jour ses fichiers dans la nuit qui suit les matchs).
- ``footprono.follow_live`` toutes les 2 minutes : score en direct, puis résultat
  et statistiques dès la fin du match (aucune requête sans match en cours).
- ``footprono.collect_odds`` à 07:30 et 16:30 : cotes des bookmakers des matchs à venir.
- ``footprono.predict_upcoming`` à 07:45 (après l'ingestion) et à 16:45 (nouveaux
  calendriers, arbitres désignés) : prédictions des 10 prochains jours.
Règlement des paris et notifications viendront dans les phases suivantes.
"""

from celery import Celery
from celery.schedules import crontab

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
        beat_schedule={
            "ingest-current-season": {
                "task": "footprono.ingest_current_season",
                "schedule": crontab(hour=6, minute=15),
            },
            "follow-live": {
                "task": "footprono.follow_live",
                "schedule": crontab(minute="*/2"),
                # Une exécution manquée est remplacée par la suivante, pas rattrapée.
                "options": {"expires": 110},
            },
            "collect-odds": {
                "task": "footprono.collect_odds",
                "schedule": crontab(hour="7,16", minute=30),
            },
            "predict-upcoming": {
                "task": "footprono.predict_upcoming",
                "schedule": crontab(hour="7,16", minute=45),
            },
        },
    )
    app.autodiscover_tasks(["footprono.worker"], related_name="tasks")
    return app


celery_app = create_celery()
