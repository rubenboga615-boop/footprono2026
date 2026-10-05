"""Tâches de la console : création, exécution en arrière-plan, journal, arrêt.

Une tâche est créée par l'API (statut ``queued``), exécutée par le worker Celery
(``running`` puis ``succeeded``, ``failed`` ou ``cancelled``) et suivie par la
console : progression, journal ligne à ligne, résumé final. L'administrateur
reçoit une notification à la fin.

Le journal est écrit par paquets (toutes les ``FLUSH_SECONDS``) par une boucle
à part : les actions appellent ``ctx.log`` sans attendre la base, y compris
depuis les fonctions de progression synchrones des ingestions. Chaque écriture
renouvelle le signe de vie (``heartbeat_at``) et relit la demande d'arrêt.

Une tâche « running » sans signe de vie depuis ``STALE_AFTER`` a été
interrompue (redémarrage du téléphone ou du serveur) : elle est marquée en
échec et ne bloque plus les tâches exclusives.
"""

import asyncio
import contextlib
import logging
import traceback
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import status
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.accounts.models import User
from footprono.cache.redis import create_redis
from footprono.console.models import AdminJob, AdminJobLine
from footprono.console.registry import get_action
from footprono.core.config import Settings
from footprono.core.errors import AppError, NotFoundError
from footprono.notifications import service as notifications
from footprono.notifications.push import sender_or_none as push_sender_or_none

logger = logging.getLogger(__name__)

FLUSH_SECONDS = 1.5
STALE_AFTER = timedelta(minutes=30)
MAX_LINES = 30_000
MAX_LINE_LENGTH = 2_000
ACTIVE = ("queued", "running")
INTERRUPTED = "interrompue (redémarrage du serveur ou du téléphone)"

Dispatcher = Callable[[int], Awaitable[None]]


class JobConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "job_conflict"


class JobStoppedError(Exception):
    """Levée par ``ctx.check_stop()`` quand l'administrateur a demandé l'arrêt."""


class JobContext:
    """Ce que voit une action : journal, progression, arrêt, session, réglages."""

    def __init__(
        self, factory: async_sessionmaker[AsyncSession], settings: Settings, job_id: int
    ) -> None:
        self.factory = factory
        self.settings = settings
        self.job_id = job_id
        self.result: dict[str, Any] | None = None
        self.stop_requested = False
        self._lines: list[str] = []
        self._written = 0
        self._dropped = 0
        self._progress: float | None = None
        self._progress_dirty = False
        self._step: int | None = None
        self._step_dirty = False

    def log(self, message: str) -> None:
        """Ajoute une ou plusieurs lignes au journal (écrites au prochain paquet)."""
        for line in str(message).splitlines() or [""]:
            if self._written + len(self._lines) >= MAX_LINES:
                self._dropped += 1
                continue
            self._lines.append(line[:MAX_LINE_LENGTH])

    def progress(self, fraction: float) -> None:
        """Avancement entre 0 et 1 (barre de progression de la console)."""
        self._progress = min(1.0, max(0.0, float(fraction)))
        self._progress_dirty = True

    def step(self, index: int) -> None:
        """Étape en cours (indice dans ``Action.steps``), affichée dans le suivi."""
        self._step = index
        self._step_dirty = True

    @property
    def files_dir(self) -> Path:
        """Dossier des fichiers téléchargeables (page « Fichiers » de la console)."""
        from footprono.console.files import files_dir

        return files_dir(self.settings)

    def check_stop(self) -> None:
        """À appeler entre deux étapes sûres : arrête la tâche si c'est demandé."""
        if self.stop_requested:
            raise JobStoppedError

    async def flush(self) -> None:
        lines, self._lines = self._lines, []
        values: dict[str, Any] = {"heartbeat_at": datetime.now(UTC)}
        if self._progress_dirty:
            values["progress"] = self._progress
            self._progress_dirty = False
        if self._step_dirty:
            values["step"] = self._step
            self._step_dirty = False
        async with self.factory() as session, session.begin():
            for line in lines:
                self._written += 1
                session.add(AdminJobLine(job_id=self.job_id, n=self._written, text=line))
            await session.execute(
                update(AdminJob).where(AdminJob.id == self.job_id).values(**values)
            )
            self.stop_requested = bool(
                await session.scalar(
                    select(AdminJob.stop_requested).where(AdminJob.id == self.job_id)
                )
            )

    async def _flush_forever(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_SECONDS)
            try:
                await self.flush()
            except Exception:  # base momentanément injoignable : réessayé au paquet suivant
                logger.exception("console_flush_failed", extra={"job_id": self.job_id})

    async def finish(self) -> None:
        if self._dropped:
            self._lines.append(f"… {self._dropped} lignes de journal non conservées (limite)")
            self._dropped = 0
        await self.flush()


async def _expire_stale(session: AsyncSession) -> None:
    """Tâches sans signe de vie : interrompues (ne bloquent plus les suivantes)."""
    limit = datetime.now(UTC) - STALE_AFTER
    await session.execute(
        update(AdminJob)
        .where(
            AdminJob.status.in_(ACTIVE),
            func.coalesce(AdminJob.heartbeat_at, AdminJob.created_at) < limit,
        )
        .values(status="failed", summary=INTERRUPTED, finished_at=datetime.now(UTC))
    )


async def create_job(
    session: AsyncSession, action_id: str, params: dict[str, Any], user: User
) -> AdminJob:
    """Vérifie les réglages et l'absence de conflit, puis enregistre la tâche (``queued``)."""
    action = get_action(action_id)
    clean = action.validate(params)
    # Deux clics simultanés : un seul passe le contrôle des conflits.
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('admin_jobs'))"))
    await _expire_stale(session)
    # Conflit : la même action déjà en cours, ou une autre grosse tâche pour une grosse tâche.
    clash = AdminJob.action == action.id
    if action.exclusive:
        clash = or_(clash, AdminJob.exclusive.is_(True))
    conflict = await session.scalar(
        select(AdminJob).where(AdminJob.status.in_(ACTIVE), clash).order_by(AdminJob.id).limit(1)
    )
    if conflict is not None:
        if conflict.action == action.id:
            message = f"cette action est déjà en cours (tâche n°{conflict.id})"
        else:
            message = (
                f"« {action_id_title(conflict.action)} » est en cours (tâche n°{conflict.id}) : "
                "une seule grosse tâche à la fois"
            )
        raise JobConflictError(message)
    job = AdminJob(
        action=action.id,
        params=clean,
        status="queued",
        exclusive=action.exclusive,
        user_id=user.id,
    )
    session.add(job)
    await session.flush()
    return job


async def run_job(
    factory: async_sessionmaker[AsyncSession], settings: Settings, job_id: int
) -> str:
    """Exécute la tâche (worker) ; renvoie son statut final."""
    async with factory() as session, session.begin():
        job = await session.get(AdminJob, job_id, with_for_update=True)
        if job is None:
            return "missing"
        if job.status == "running":
            # Message redistribué après un arrêt brutal : l'exécution précédente est perdue.
            job.status, job.summary = "failed", INTERRUPTED
            job.finished_at = datetime.now(UTC)
            return job.status
        if job.status != "queued":
            return job.status
        job.status = "running"
        job.started_at = job.heartbeat_at = datetime.now(UTC)
        action_id, params = job.action, dict(job.params)

    ctx = JobContext(factory, settings, job_id)
    flusher = asyncio.create_task(ctx._flush_forever())
    result_status, summary = "failed", ""
    try:
        action = get_action(action_id)
        ctx.log(f"Démarrage : {action.title}")
        summary = await action.run(ctx, params)
        result_status = "succeeded"
    except JobStoppedError:
        result_status, summary = "cancelled", "arrêtée à la demande de l'administrateur"
    except Exception as exc:
        logger.exception("console_job_failed", extra={"job_id": job_id, "action": action_id})
        ctx.log("Erreur :")
        ctx.log("".join(traceback.format_exception_only(exc)).strip())
        summary = f"échec : {exc}" if str(exc) else f"échec : {type(exc).__name__}"
    finally:
        flusher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await flusher
    ctx.log(f"Fin : {summary}")
    await ctx.finish()

    async with factory() as session:
        async with session.begin():
            job = await session.get(AdminJob, job_id)
            if job is None:
                return "missing"
            job.status = result_status
            job.summary = summary[:400]
            job.result = ctx.result
            job.finished_at = datetime.now(UTC)
            if result_status == "succeeded":
                job.progress = 1.0
        await _publish(session, settings)
    return result_status


def action_id_title(action_id: str) -> str:
    try:
        return get_action(action_id).title
    except AppError:
        return action_id


async def _publish(session: AsyncSession, settings: Settings) -> None:
    redis = create_redis(settings)
    push = push_sender_or_none(settings)
    try:
        await notifications.publish_pending(session, redis, push)
    except Exception:  # la notification reste en base
        logger.exception("console_notify_failed")
    finally:
        await redis.aclose()
        if push is not None:
            await push.aclose()


async def request_stop(session: AsyncSession, job_id: int) -> AdminJob:
    job = await session.get(AdminJob, job_id, with_for_update=True)
    if job is None:
        raise NotFoundError("tâche introuvable")
    if job.status == "queued":
        job.status, job.summary = "cancelled", "annulée avant son démarrage"
        job.finished_at = datetime.now(UTC)
    elif job.status == "running":
        if not get_action(job.action).stoppable:
            raise JobConflictError("cette action ne peut pas être arrêtée en cours de route")
        job.stop_requested = True
    else:
        raise JobConflictError("la tâche est déjà terminée")
    return job


def job_out(job: AdminJob) -> dict[str, Any]:
    now = datetime.now(UTC)
    heartbeat = job.heartbeat_at or job.created_at
    silent = (now - heartbeat).total_seconds() if heartbeat else None
    # Temps restant estimé d'après la progression (affiché à partir de 2 %).
    eta = None
    if job.status == "running" and job.started_at and job.progress and job.progress >= 0.02:
        elapsed = (now - job.started_at).total_seconds()
        eta = round(elapsed * (1 - job.progress) / job.progress)
    return {
        "id": job.id,
        "action": job.action,
        "title": action_id_title(job.action),
        "params": job.params,
        "status": job.status,
        "progress": job.progress,
        "summary": job.summary,
        "result": job.result,
        "stop_requested": job.stop_requested,
        "user_id": job.user_id,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "silent_seconds": round(silent) if silent is not None and job.status in ACTIVE else None,
        "step": job.step,
        "eta_seconds": eta,
    }


async def job_detail(session: AsyncSession, job_id: int, after: int = 0) -> dict[str, Any]:
    """La tâche et les lignes de journal après la n° ``after`` (suivi en direct)."""
    job = await session.get(AdminJob, job_id)
    if job is None:
        raise NotFoundError("tâche introuvable")
    lines = (
        await session.execute(
            select(AdminJobLine.n, AdminJobLine.at, AdminJobLine.text)
            .where(AdminJobLine.job_id == job_id, AdminJobLine.n > after)
            .order_by(AdminJobLine.n)
            .limit(1000)
        )
    ).all()
    return {
        **job_out(job),
        "lines": [{"n": n, "at": at, "text": t} for n, at, t in lines],
    }


async def list_jobs(
    session: AsyncSession, limit: int = 50, action: str | None = None
) -> list[dict[str, Any]]:
    await _expire_stale(session)
    query = select(AdminJob).order_by(AdminJob.id.desc()).limit(limit)
    if action is not None:
        query = query.where(AdminJob.action == action)
    return [job_out(j) for j in (await session.scalars(query)).all()]


async def celery_dispatch(job_id: int) -> None:
    """Envoie la tâche au worker (remplacé dans les tests par une exécution directe)."""
    from footprono.worker.tasks import run_admin_job

    run_admin_job.delay(job_id)
