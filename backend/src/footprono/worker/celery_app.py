"""Application Celery : tâches de fond et planification.

Lancement :
    celery -A footprono.worker.celery_app worker --loglevel=INFO
    celery -A footprono.worker.celery_app beat   --loglevel=INFO

Tâches planifiées (UTC) :
- ``footprono.ingest_current_season`` chaque matin à 06:15 (football-data met
  à jour ses fichiers dans la nuit qui suit les matchs).
- ``footprono.follow_live`` toutes les 2 minutes : score en direct, puis résultat
  et statistiques dès la fin du match (aucune requête sans match en cours) ;
  règlement des paris et des coupons du jour, et notification « coupons du jour
  disponibles » dès que tous leurs codes 1xBet sont saisis.
- ``footprono.collect_odds`` toutes les 3 heures (01:30, 04:30, 07:30… 22:30) :
  cotes des bookmakers des matchs à venir (20 à 50 requêtes par relevé).
- ``footprono.predict_upcoming`` à 07:45 (après l'ingestion) et à 16:45 (nouveaux
  calendriers, arbitres désignés) : prédictions des 10 prochains jours.
- ``footprono.predict_if_needed`` au démarrage du worker, toutes les heures (:10)
  et après chaque collecte des cotes : prédit seulement si la dernière exécution
  a plus de 12 h ou si de nouveaux matchs sont arrivés au calendrier.
- ``footprono.daily_smart_coupons`` à 08:05 : coupons intelligents du jour
  (un par profil), réglés avec les paris.
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
            # 07:30 reste avant les prédictions (07:45) et les coupons du jour (08:05).
            "collect-odds": {
                "task": "footprono.collect_odds",
                "schedule": crontab(hour="1,4,7,10,13,16,19,22", minute=30),
                "options": {"expires": 3 * 3600 - 300},
            },
            "predict-upcoming": {
                "task": "footprono.predict_upcoming",
                "schedule": crontab(hour="7,16", minute=45),
            },
            # Rattrapage : ne calcule que si les prédictions ont plus de 12 h ou
            # si de nouveaux matchs sont arrivés (sinon une simple requête).
            "predict-if-needed": {
                "task": "footprono.predict_if_needed",
                "schedule": crontab(minute=10),
                "options": {"expires": 3000},
            },
            # Coupons du jour (après cotes 07:30 et prédictions 07:45).
            "daily-smart-coupons": {
                "task": "footprono.daily_smart_coupons",
                "schedule": crontab(hour=8, minute=5),
            },
            # Alertes de l'administrateur (ntfy) : pannes, tâches en échec, quota, sauvegarde.
            "alerts-watchdog": {
                "task": "footprono.alerts_watchdog",
                "schedule": crontab(minute="3,13,23,33,43,53"),
                "options": {"expires": 500},
            },
            # Rappel avant la fin de Premium (3 jours avant, la veille), en fin de matinée.
            "premium-reminders": {
                "task": "footprono.premium_reminders",
                "schedule": crontab(hour=10, minute=5),
            },
            # Paiements dont la notification CinetPay n'est pas arrivée.
            "check-payments": {
                "task": "footprono.check_payments",
                "schedule": crontab(minute="*/10"),
                "options": {"expires": 500},
            },
        },
    )
    app.autodiscover_tasks(["footprono.worker"], related_name="tasks")
    return app


celery_app = create_celery()
