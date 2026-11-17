"""« Tout rattraper » (demande du fondateur du 17/11/2026, docs/AUDIT_JEU_2026-11-16.md).

Le 16/11/2026, une collecte d'historique avait vidé le quota API-Football : aucun direct,
aucun résultat, des paris bloqués toute la journée ; le quota revenu, rien ne rattrapait ce
qui avait été manqué (une tâche du planificateur manquée n'est jamais rejouée).

En une fois, dans l'ordre, et chaque étape sautée si elle est à jour :

0. bilan : quota, requêtes estimées, matchs en retard, paris en attente, tâches manquées ;
   refusé si le rattrapage entamerait la réserve du direct du jour ;
1. matchs en retard (heure passée, pas terminés en base, 7 jours au plus) redemandés par
   lots de 20 : score, mi-temps, statut, événements, nouvelle heure ;
2. règlement : paris (une notification de synthèse par joueur, aucune notification du
   direct), montantes, coupons du jour, propositions du coupon en direct et des moteurs ;
3. cotes, si le dernier relevé a plus de 3 heures ;
4. prédictions, si elles ne sont plus à jour ;
5. coupons du jour, s'ils manquent après 08:05 ;
6. pages gardées prêtes : Fiabilité, chances des moteurs.

Un verrou empêche deux rattrapages en même temps ; le relancer ne règle ni ne notifie rien
deux fois (le règlement ne touche qu'aux paris encore ouverts). Lancé depuis la console
(« Tout rattraper »), chaque nuit à 00:10 GMT, et dès que le direct retrouve du quota.
"""

import math
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.bookmaker import engine_compare, live_coupons, settlement, smart_coupon
from footprono.bookmaker.models import Bet
from footprono.bookmaker.smart_models import SmartCoupon
from footprono.cache.redis import create_redis
from footprono.core.config import Settings
from footprono.football.models import BookmakerOdds, Match
from footprono.ingestion import live, service
from footprono.ingestion.sources import api_football
from footprono.ingestion.sources.api_football import UNPLAYED_STATUSES
from footprono.notifications.push import sender_or_none as push_sender_or_none
from footprono.predictions import service as prediction_service

LOCK = "catch_up:lock"
LOCK_SECONDS = 3600
# Drapeau posé par le suivi du direct quand il s'arrête faute de quota : le premier passage
# qui retrouve du quota lance le rattrapage.
QUOTA_STOPPED_FLAG = "catch_up:live_quota_stopped"
ODDS_STALE = timedelta(hours=3)
DAILY_COUPONS_AT = time(8, 5)
# Requêtes du reste de la journée hors direct (résultats du matin, blessés, cotes) : marge.
OTHER_MARGIN = 300
# Relevé des cotes : environ une requête par championnat et par page (estimation).
ODDS_COST = 60
STEPS = (
    "Bilan",
    "Matchs en retard",
    "Règlement",
    "Cotes",
    "Prédictions",
    "Coupons du jour",
    "Pages et caches",
    "Compte rendu",
)


class CatchUpRefusedError(Exception):
    """Rattrapage refusé avant de commencer (quota insuffisant, déjà en cours)."""


async def assess(session: AsyncSession, settings: Settings, now: datetime) -> dict[str, Any]:
    """Étape 0 : ce qui est en retard, ce que ça coûtera, et ce que le direct doit garder."""
    late = await live.late_matches(session, now)
    open_bets = await session.scalar(select(func.count()).where(Bet.status == "open")) or 0
    last_odds = await session.scalar(select(func.max(BookmakerOdds.fetched_at)))
    odds_due = last_odds is None or now - last_odds > ODDS_STALE
    predictions_due = await prediction_service.prediction_needed(session, now)
    coupons_due = await _daily_coupons_due(session, now)
    need = await live.live_need(session, now)
    cost = math.ceil(len(late) / live.IDS_PER_REQUEST) + len(late) + (ODDS_COST if odds_due else 0)
    remaining: int | None = None
    if settings.api_football_key is not None:
        async with api_football.ApiFootballClient(
            settings.api_football_key.get_secret_value(),
            budget=settings.api_football_budget,
            min_remaining=settings.api_football_min_remaining,
            transport=service.api_football_transport,
        ) as client:
            await client.status()  # ne consomme pas de quota
            remaining = client.day_remaining
    reserve = settings.api_football_min_remaining + need["requests"] + OTHER_MARGIN
    missed = [
        label
        for label, due in (
            ("relevé des cotes (plus de 3 h)", odds_due),
            (f"prédictions ({predictions_due})", predictions_due is not None),
            ("coupons du jour", coupons_due),
        )
        if due
    ]
    return {
        "remaining": remaining,
        "late": len(late),
        "open_bets": int(open_bets),
        "cost": cost,
        "live_need": need,
        "reserve": reserve,
        "missed": missed,
        "odds_due": odds_due,
        "predictions_due": predictions_due is not None,
        "coupons_due": coupons_due,
        "allowed": remaining is None or remaining - cost >= reserve,
    }


async def _daily_coupons_due(session: AsyncSession, now: datetime) -> bool:
    """Coupons du jour pas encore faits, alors que leur heure (08:05) est passée."""
    if now.astimezone(UTC).time() < DAILY_COUPONS_AT:
        return False
    found = await session.scalar(
        select(func.count()).where(SmartCoupon.day == now.date(), SmartCoupon.engine == 1)
    )
    return not found


def describe(plan: dict[str, Any]) -> list[str]:
    """Bilan lisible, affiché avant de commencer."""
    need = plan["live_need"]
    remaining = "inconnu (pas de clé)" if plan["remaining"] is None else str(plan["remaining"])
    return [
        f"Quota API-Football restant aujourd'hui : {remaining}",
        f"Requêtes estimées pour le rattrapage : {plan['cost']}",
        f"Réserve gardée pour le direct du jour : {plan['reserve']} "
        f"({need['matches']} match(s) suivis encore aujourd'hui, environ {need['requests']} "
        f"requêtes, plus la marge du serveur)",
        f"Matchs en retard : {plan['late']}",
        f"Paris en attente : {plan['open_bets']}",
        "Tâches manquées : " + (", ".join(plan["missed"]) if plan["missed"] else "aucune"),
    ]


async def run(
    settings: Settings,
    factory: async_sessionmaker[AsyncSession],
    *,
    log: Callable[[str], None] = lambda _m: None,
    step: Callable[[int], None] = lambda _i: None,
    check_stop: Callable[[], None] = lambda: None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Rattrape tout ce qui a été mis en attente ; renvoie le compte rendu (étape 8)."""
    from footprono.worker import tasks  # tâches existantes (import circulaire sinon)

    now = now or datetime.now(UTC)
    redis = create_redis(settings)
    try:
        if not await redis.set(LOCK, now.isoformat(), nx=True, ex=LOCK_SECONDS):
            raise CatchUpRefusedError("un rattrapage est déjà en cours")
        try:
            return await _run(settings, factory, redis, tasks, log, step, check_stop, now)
        finally:
            await redis.delete(LOCK)
    finally:
        await redis.aclose()


async def _run(
    settings: Settings,
    factory: async_sessionmaker[AsyncSession],
    redis: Any,
    tasks: Any,
    log: Callable[[str], None],
    step: Callable[[int], None],
    check_stop: Callable[[], None],
    now: datetime,
) -> dict[str, Any]:
    step(0)
    async with factory() as session:
        plan = await assess(session, settings, now)
    for line in describe(plan):
        log(line)
    if not plan["allowed"]:
        raise CatchUpRefusedError(
            f"quota insuffisant : {plan['remaining']} restantes, {plan['cost']} pour le "
            f"rattrapage, {plan['reserve']} à garder pour le direct du jour. Relance-le après "
            "minuit GMT (remise à zéro du quota) : il tourne aussi tout seul à 00:10."
        )
    report: dict[str, Any] = {"plan": {k: v for k, v in plan.items() if k != "live_need"}}
    used = 0

    check_stop()
    step(1)
    if plan["late"]:
        async with factory() as session:
            followed = await live.follow_live(session, settings, now, log, catch_up=True)
        used += int(followed.get("requests") or 0)
        report["matches"] = {
            "finished": followed.get("finished", []),
            "updated": len(set(followed.get("updated", []))),
            "status": followed.get("status"),
        }
        log(f"Matchs terminés récupérés : {len(followed.get('finished', []))}")
    else:
        log("Aucun match en retard.")

    check_stop()
    step(2)
    push = push_sender_or_none(settings)
    try:
        async with factory() as session:
            bets = await settlement.settle_bets(session, redis=redis, push=push, catch_up=True)
    finally:
        if push is not None:
            await push.aclose()
    async with factory() as session:
        coupons = await smart_coupon.settle_pending(session)
    async with factory() as session:
        live_picks = await live_coupons.settle_picks(session)
    async with factory() as session:
        proposals = await engine_compare.settle_proposals(session)
    report["settlement"] = {
        "bets": bets["outcomes"],
        "montantes": bets["montantes"],
        "notified": bets.get("notified", 0),
        "daily_coupons": coupons,
        "live_picks": live_picks,
        "engine_proposals": proposals,
    }
    o = bets["outcomes"]
    log(
        f"Paris réglés : {bets['settled']} (gagnés {o.get('won', 0) + o.get('partial', 0)}, "
        f"perdus {o.get('lost', 0)}, remboursés {o.get('push', 0)}) ; montantes avancées "
        f"{bets['montantes']['advanced']}, arrêtées {bets['montantes']['stopped']} ; "
        f"notifications {bets.get('notified', 0)}"
    )

    check_stop()
    step(3)
    if plan["odds_due"]:
        odds = await tasks._collect_odds()
        used += int((odds.get("odds") or {}).get("requests") or 0)
        used += int((odds.get("injuries") or {}).get("requests") or 0)
        log("Cotes relevées.")
        report["odds"] = True
    else:
        log("Cotes à jour.")

    check_stop()
    step(4)
    report["predictions"] = await tasks._predict_upcoming(only_if_needed=True)
    log(f"Prédictions : {report['predictions'].get('status', 'faites')}")

    check_stop()
    step(5)
    async with factory() as session:
        due = await _daily_coupons_due(session, now)
    if due:
        async with factory() as session:
            report["daily_coupons"] = await smart_coupon.create_daily(session)
        async with factory() as session:
            report["daily_coupons_engine2"] = await smart_coupon.create_daily(session, engine=2)
        log("Coupons du jour créés (ils sont annoncés aux joueurs quand leurs codes sont saisis).")
    else:
        log("Coupons du jour : rien à faire.")

    check_stop()
    step(6)
    report["reliability"] = await tasks._warm_reliability()
    report["engine_chances"] = await tasks._engine_chances()

    step(7)
    async with factory() as session:
        left = await live.late_matches(session, now)
        open_bets = await session.scalar(select(func.count()).where(Bet.status == "open")) or 0
    report["requests"] = used
    report["still_late"] = [_why(m) for m in left]
    report["open_bets"] = int(open_bets)
    log(f"Requêtes utilisées : {used}")
    if left:
        log(f"Encore en attente : {len(left)} match(s)")
        for line in report["still_late"][:20]:
            log(f"  {line}")
    await redis.delete(QUOTA_STOPPED_FLAG)
    return report


def _why(match: Match) -> str:
    """Pourquoi un match reste en attente après le rattrapage."""
    status = match.api_status or "?"
    if status in UNPLAYED_STATUSES:
        reason = "reporté, annulé ou arrêté selon la source (remboursé après 48 h confirmées)"
    elif status in ("NS", "TBD"):
        reason = "pas commencé selon la source (heure à confirmer)"
    elif match.live_minute is not None:
        reason = "en cours selon la source"
    else:
        reason = "pas encore remis à jour (quota, ou absent de la réponse)"
    kickoff = f"{match.kickoff_at:%d/%m %H:%M}" if match.kickoff_at else "date inconnue"
    return f"match {match.id} ({kickoff} GMT, {status}) : {reason}"


def summary(report: dict[str, Any]) -> str:
    """Une ligne pour l'historique des actions."""
    s = report.get("settlement", {})
    o = s.get("bets", {})
    m = s.get("montantes", {})
    finished = len((report.get("matches") or {}).get("finished", []))
    return (
        f"{finished} match(s) mis à jour, paris gagnés {o.get('won', 0) + o.get('partial', 0)}, "
        f"perdus {o.get('lost', 0)}, remboursés {o.get('push', 0)} ; montantes avancées "
        f"{m.get('advanced', 0)}, arrêtées {m.get('stopped', 0)} ; {s.get('notified', 0)} "
        f"notification(s) ; {report.get('requests', 0)} requête(s) ; "
        f"{len(report.get('still_late', []))} match(s) encore en attente"
    )


__all__ = ["STEPS", "CatchUpRefusedError", "assess", "describe", "run", "summary"]
