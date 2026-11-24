"""Tâches de fond."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from celery.signals import worker_ready
from sqlalchemy.ext.asyncio import AsyncEngine

from footprono import __version__, alerts
from footprono.accounts.reminders import send_premium_reminders
from footprono.bookmaker import (
    closing,
    live_coupons,
    odds_alerts,
    playable,
    settlement,
    smart_coupon,
)
from footprono.bookmaker.kickoff import send_kickoff_reminders
from footprono.cache.redis import create_redis
from footprono.console import jobs as console_jobs
from footprono.console.runs import tracked
from footprono.core.config import Settings, get_settings
from footprono.core.errors import AppError
from footprono.db.session import create_engine, create_session_factory
from footprono.football.models import DataSource
from footprono.ingestion import cups, live, nations
from footprono.ingestion.reference import COMPETITIONS, current_season
from footprono.ingestion.service import IngestionRequest, run_ingestion
from footprono.notifications import live_feed
from footprono.notifications import service as notifications
from footprono.notifications.push import sender_or_none as push_sender_or_none
from footprono.payments import service as payment_service
from footprono.predictions import cups as cup_predictions
from footprono.predictions import nations as nation_predictions
from footprono.predictions import reliability
from footprono.predictions import service as prediction_service
from footprono.predictions.publication import publication
from footprono.worker import catchup
from footprono.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _settle(engine: AsyncEngine, settings: Settings) -> dict[str, Any]:
    """Règle les paris ; notifications en direct (Redis) et sur téléphone (Firebase)."""
    redis = create_redis(settings)
    push = push_sender_or_none(settings)
    try:
        if await redis.exists(catchup.SETTLE_LOCK):
            # « Tout rattraper » en train de régler (étape 2) : c'est lui qui règle, en une
            # notification de synthèse par joueur (sinon une par pari, au milieu de la nuit).
            return {"skipped": "rattrapage en cours"}
        async with create_session_factory(engine)() as session:
            report = await settlement.settle_bets(session, redis=redis, push=push)
        async with create_session_factory(engine)() as session:
            report["smart_coupons"] = await smart_coupon.settle_pending(session)
        async with create_session_factory(engine)() as session:
            report["live_picks"] = await live_coupons.settle_picks(session)
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
        # Coupes d'Europe : calendrier et résultats (une requête par coupe). Une panne ici
        # n'empêche pas les championnats : elle est consignée dans le rapport.
        try:
            async with create_session_factory(engine)() as session:
                cup_report = await cups.update_cups(session, settings)
        except Exception as exc:  # source extérieure : consignée, jamais bloquante
            logger.warning("cups_update_failed", extra={"error": str(exc)})
            cup_report = {"status": "failed", "error": str(exc)[:300]}
        # Sélections nationales : même principe (deux requêtes par compétition).
        try:
            async with create_session_factory(engine)() as session:
                nation_report = await nations.update_nations(session, settings)
        except Exception as exc:  # source extérieure : consignée, jamais bloquante
            logger.warning("nations_update_failed", extra={"error": str(exc)})
            nation_report = {"status": "failed", "error": str(exc)[:300]}
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
        "cups": {k: cup_report.get(k) for k in ("status", "season", "cups", "error")},
        "nations": {k: nation_report.get(k) for k in ("status", "competitions", "error")},
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
        report["playable"] = await _refresh_playable(engine, settings)
    finally:
        await engine.dispose()
    # Le calendrier vient d'être synchronisé : nouveaux matchs prédits sans attendre.
    predict_if_needed.delay()
    # Cotes nouvelles : alertes de cote des joueurs.
    check_odds_alerts.delay()
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

    Sans match en cours, ne fait aucune requête : planifié chaque minute.
    """
    return asyncio.run(_follow_live())


# Un seul passage à la fois : chaque minute, un passage lent (fin de plusieurs matchs,
# statistiques, règlements) ne doit pas en chevaucher un autre.
FOLLOW_LOCK = "lock:follow_live"


async def _follow_live() -> dict[str, Any]:
    settings = get_settings()
    lock = create_redis(settings)
    try:
        if not await lock.set(FOLLOW_LOCK, "1", nx=True, ex=300):
            return {"status": "idle", "requests": 0, "skipped": "passage précédent en cours"}
        try:
            return await _follow_live_once(settings)
        finally:
            await lock.delete(FOLLOW_LOCK)
    finally:
        await lock.aclose()


async def _follow_live_once(settings: Settings) -> dict[str, Any]:
    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            report = await live.follow_live(session, settings)
        # Direct arrêté faute de quota (16/11/2026) : noté pour l'alerte de la console ; au
        # premier passage qui retrouve du quota, tout ce qui a été manqué est rattrapé.
        flag = create_redis(settings)
        try:
            if report.get("status") == live.QUOTA_STOPPED:
                await flag.set(catchup.QUOTA_STOPPED_FLAG, datetime.now(UTC).isoformat())
            elif report.get("status") == "ok" and await flag.get(catchup.QUOTA_STOPPED_FLAG):
                await flag.delete(catchup.QUOTA_STOPPED_FLAG)
                catch_up.delay()
                report["catch_up"] = "lancé (le quota est revenu)"
        finally:
            await flag.aclose()
        # Règlement juste après : un pari est payé dès la fin de son match.
        report["bets"] = await _settle(engine, settings)
        # Puis le relevé poussé à l'application ouverte, réglements compris (retour du
        # fondateur du 12/11/2026 : il fallait actualiser sans arrêt).
        updated = report.pop("updated", [])
        odds = report.pop("live_odds", {})
        if updated or odds:
            redis = create_redis(settings)
            try:
                # Cotes en direct du coupon en direct (gardées 3 minutes), avec le score et
                # les cartons rouges du moment : une cote d'avant un but n'est plus jouable.
                if odds:
                    async with create_session_factory(engine)() as session:
                        states = await live_coupons.match_states(session, list(odds))
                    for mid, data in odds.items():
                        data["state"] = states.get(mid)
                await live_coupons.store_odds(redis, odds)
                # Fiabilité (D15) : propositions du moment enregistrées une fois.
                if odds:
                    async with create_session_factory(engine)() as session:
                        report["live_picks"] = await live_coupons.record_proposals(session, redis)
                        # Cotes de chaque fenêtre, pour l'étude avec les statistiques du direct.
                        report["live_window_odds"] = await live_coupons.record_window_odds(
                            session, redis
                        )
                report["live_odds"] = len(odds)
                if updated:
                    async with create_session_factory(engine)() as session:
                        report["pushed"] = await live_feed.publish_live(redis, session, updated)
            finally:
                await redis.aclose()
        return report
    finally:
        await engine.dispose()


@celery_app.task(name="footprono.catch_up")
@tracked("catch_up")
def catch_up() -> dict[str, Any]:
    """« Tout rattraper » : matchs en retard, règlement, cotes, prédictions, coupons du jour.
    Chaque nuit à 00:10 GMT (quota remis à zéro) et dès que le direct retrouve du quota."""
    return asyncio.run(_catch_up())


async def _catch_up() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        report = await catchup.run(settings, create_session_factory(engine), log=logger.info)
        return {"summary": catchup.summary(report), "requests": report.get("requests", 0)}
    except catchup.CatchUpRefusedError as exc:
        return {"status": "skipped", "reason": str(exc)}
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
            # Interrupteurs de la console (départ : FP_CUPS_PREDICTIONS, FP_NATIONS_PREDICTIONS).
            published = await publication(session, get_settings())
            # Coupes d'Europe : moteur à part ; une erreur n'annule pas les championnats.
            try:
                if not published.cups:
                    raise _CupsDisabled
                cup_run = await cup_predictions.predict_cups(session)
                report["cups"] = {"run_id": cup_run.id, **cup_run.report}
            except _CupsDisabled:
                report["cups"] = {"status": "disabled"}
            except Exception as exc:  # source extérieure : consignée, jamais bloquante
                logger.warning("cups_predict_failed", extra={"error": str(exc)})
                report["cups"] = {"status": "failed", "error": str(exc)[:300]}
            # Sélections nationales : même principe.
            if not published.nations:
                report["nations"] = {"status": "disabled"}
            else:
                try:
                    nation_run = await nation_predictions.predict_nations(session)
                    report["nations"] = {"run_id": nation_run.id, **nation_run.report}
                except Exception as exc:  # jamais bloquante pour les championnats
                    logger.warning("nations_predict_failed", extra={"error": str(exc)})
                    report["nations"] = {"status": "failed", "error": str(exc)[:300]}
        report["playable"] = await _refresh_playable(engine, get_settings())
        return {"run_id": run.id, "status": run.status, "reason": reason, "report": report}
    finally:
        await engine.dispose()


async def _refresh_playable(engine: AsyncEngine, settings: Settings) -> dict[str, Any]:
    """Sélections jouables préparées pour le Coupon intelligent et les suggestions
    (bookmaker/playable.py). Un échec ne bloque rien : les demandes calculent alors elles-mêmes."""
    redis = create_redis(settings)
    try:
        async with create_session_factory(engine)() as session:
            return {"matches": await playable.refresh(session, redis)}
    except Exception as exc:  # jamais bloquant : calcul direct à la demande
        logger.warning("playable_refresh_failed", extra={"error": str(exc)})
        return {"status": "failed", "error": str(exc)[:300]}
    finally:
        await redis.aclose()


class _CupsDisabled(Exception):
    """Pronostics des coupes désactivés (interrupteur de la console)."""


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
    # Tous les prestataires configurés, Wave Business compris (rapport du 14/11/2026, P1 :
    # avant, un paiement Wave dont la notification se perdait n'était jamais revérifié).
    if not payment_service.available_providers(settings):
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
    # Après une mise à jour du serveur, les sélections jouables sont préparées tout de
    # suite (sinon le Coupon intelligent attendait la collecte des cotes suivante, 3 h).
    refresh_playable.apply_async(countdown=20)
    # Page Fiabilité calculée d'avance : le premier visiteur n'attend plus 6 à 7 s.
    warm_reliability.apply_async(countdown=25)


@celery_app.task(name="footprono.warm_reliability")
def warm_reliability() -> dict[str, Any]:
    """Vues par défaut de la page Fiabilité préparées (au démarrage, puis toutes les 5 min)."""
    return asyncio.run(_warm_reliability())


async def _warm_reliability() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    redis = create_redis(settings)
    try:
        async with create_session_factory(engine)() as session:
            views = await reliability.warm_cache(session, redis, settings.reliability_cache_seconds)
        return {"views": views}
    except Exception as exc:  # jamais bloquant : la page calcule alors à la demande
        logger.warning("reliability_warm_failed", extra={"error": str(exc)})
        return {"status": "failed", "error": str(exc)[:300]}
    finally:
        await redis.aclose()
        await engine.dispose()


@celery_app.task(name="footprono.refresh_playable")
def refresh_playable() -> dict[str, Any]:
    """Sélections jouables préparées (bookmaker/playable.py)."""
    return asyncio.run(_refresh_playable_task())


async def _refresh_playable_task() -> dict[str, Any]:
    engine = create_engine(get_settings())
    try:
        return await _refresh_playable(engine, get_settings())
    finally:
        await engine.dispose()


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


@celery_app.task(name="footprono.kickoff_reminders")
@tracked("kickoff_reminders")
def kickoff_reminders() -> dict[str, Any]:
    """« Ton pari commence dans 25 min » (bookmaker/kickoff.py)."""
    return asyncio.run(_kickoff_reminders())


async def _kickoff_reminders() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    redis = create_redis(settings)
    push = push_sender_or_none(settings)
    try:
        async with create_session_factory(engine)() as session:
            sent = await send_kickoff_reminders(session)
            await notifications.publish_pending(session, redis, push)
    finally:
        await redis.aclose()
        if push is not None:
            await push.aclose()
        await engine.dispose()
    return {"status": "ok", "sent": sent}


@celery_app.task(name="footprono.odds_alerts")
@tracked("odds_alerts")
def check_odds_alerts() -> dict[str, Any]:
    """Alertes de cote des joueurs (bookmaker/odds_alerts.py) : après chaque relevé des
    cotes, et toutes les 30 minutes (alertes retenues pendant la nuit du joueur)."""
    return asyncio.run(_check_odds_alerts())


async def _check_odds_alerts() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    redis = create_redis(settings)
    push = push_sender_or_none(settings)
    try:
        async with create_session_factory(engine)() as session:
            sent = await odds_alerts.check(session)
            await notifications.publish_pending(session, redis, push)
        # Mesure en silence (24/11/2026) : occasions enregistrées, puis clôture et résultat de
        # tout ce qui a été proposé ou joué.
        async with create_session_factory(engine)() as session:
            occasions = await closing.record_occasions(session)
        async with create_session_factory(engine)() as session:
            filled = await closing.fill(session)
    finally:
        await redis.aclose()
        if push is not None:
            await push.aclose()
        await engine.dispose()
    return {"status": "ok", "triggered": sent, "occasions": occasions, "closing": filled}


@celery_app.task(name="footprono.closing_odds")
@tracked("closing_odds")
def closing_odds() -> dict[str, Any]:
    """Cotes des matchs européens relues environ 1 h avant et 5 à 20 minutes avant le coup
    d'envoi (cote de clôture, plan qualité du 24/11/2026)."""
    return asyncio.run(_closing_odds())


async def _closing_odds() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            return await live.collect_closing_odds(session, settings)
    finally:
        await engine.dispose()


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
