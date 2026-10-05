"""Console d'administration : catalogue d'actions, lancement, suivi, tableau de bord.

Réservée au rôle administrateur. Une action est enregistrée puis exécutée par le
worker ; la console suit sa progression et son journal (``after`` : lignes déjà lues).
"""

import asyncio
import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from footprono import app_release
from footprono.accounts import audit
from footprono.accounts.models import User
from footprono.api.deps import AdminUserDep, RedisDep, SessionDep, SettingsDep
from footprono.console import files, jobs
from footprono.console.dashboard import dashboard
from footprono.console.registry import catalog, get_action
from footprono.core.errors import AppError
from footprono.payments.models import Payment

router = APIRouter(prefix="/admin/console", tags=["console"])


class JobIn(BaseModel):
    action: str = Field(max_length=48)
    params: dict[str, Any] = Field(default_factory=dict)
    # Action irréversible : la console a demandé confirmation.
    confirmed: bool = False


class ConfirmationRequiredError(AppError):
    status_code = 428
    code = "confirmation_required"


@router.get("/actions")
async def list_actions(_admin: AdminUserDep) -> list[dict[str, Any]]:
    return catalog()


@router.get("/dashboard")
async def get_dashboard(
    _admin: AdminUserDep, session: SessionDep, redis: RedisDep, settings: SettingsDep
) -> dict[str, Any]:
    out = await dashboard(session, redis, settings)
    await session.commit()  # tâches sans signe de vie marquées interrompues
    return out


@router.post("/jobs", status_code=201)
async def create_job(
    body: JobIn, admin: AdminUserDep, session: SessionDep, request: Request
) -> dict[str, Any]:
    action = get_action(body.action)
    if action.risk == "irreversible" and not body.confirmed:
        raise ConfirmationRequiredError(f"« {action.title} » est irréversible : confirmer")
    job = await jobs.create_job(session, body.action, body.params, admin)
    audit.record(session, admin, "job", f"action lancée : {action.title} (tâche {job.id})")
    await session.commit()
    dispatch: jobs.Dispatcher = getattr(request.app.state, "console_dispatch", jobs.celery_dispatch)
    try:
        await dispatch(job.id)
    except Exception as exc:  # file Redis injoignable : la tâche ne restera pas « queued »
        job.status, job.summary = "failed", f"envoi au worker impossible : {exc}"[:400]
        await session.commit()
        raise AppError("envoi au worker impossible : Redis ou le worker sont arrêtés") from exc
    await session.refresh(job)
    return jobs.job_out(job)


@router.get("/jobs")
async def list_jobs(
    _admin: AdminUserDep,
    session: SessionDep,
    action: Annotated[str | None, Query(max_length=48)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    out = await jobs.list_jobs(session, limit=limit, action=action)
    await session.commit()
    return out


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: int,
    _admin: AdminUserDep,
    session: SessionDep,
    after: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return await jobs.job_detail(session, job_id, after)


@router.post("/jobs/{job_id}/stop")
async def stop_job(job_id: int, admin: AdminUserDep, session: SessionDep) -> dict[str, Any]:
    job = await jobs.request_stop(session, job_id)
    audit.record(session, admin, "job_stop", f"arrêt demandé : tâche {job_id}")
    await session.commit()
    return jobs.job_out(job)


# --- Fichiers produits par les actions ----------------------------------------


@router.get("/files")
async def list_console_files(_admin: AdminUserDep, settings: SettingsDep) -> list[dict[str, Any]]:
    return await asyncio.to_thread(files.list_files, settings)


@router.post("/files/{name}/link")
async def file_link(
    name: str, _admin: AdminUserDep, settings: SettingsDep, request: Request
) -> dict[str, str]:
    """Lien de téléchargement valable quelques minutes (le navigateur télécharge seul)."""
    prefix = f"{request.app.state.settings.api_prefix}/admin/console/download"
    return {"url": files.download_link(settings, prefix, name)}


@router.get("/download/{name}", include_in_schema=False)
async def download_file(
    name: str,
    settings: SettingsDep,
    expires: Annotated[int, Query()],
    signature: Annotated[str, Query(max_length=128)],
) -> FileResponse:
    path = files.check_link(settings, name, expires, signature)
    return FileResponse(path, filename=name, media_type="application/octet-stream")


@router.delete("/files/{name}", status_code=204)
async def delete_file(
    name: str, admin: AdminUserDep, settings: SettingsDep, session: SessionDep
) -> None:
    files.safe_path(settings, name).unlink()
    audit.record(session, admin, "file_delete", f"fichier supprimé : {name}")
    await session.commit()


# --- Versions de l'application -------------------------------------------------

MAX_APK_ARCHIVE = 400 * 1024 * 1024


@router.get("/app-release")
async def app_release_info(_admin: AdminUserDep, settings: SettingsDep) -> dict[str, Any]:
    return {"current": app_release.current(settings.app_release_dir)}


@router.post("/app-release")
async def publish_app_release(
    request: Request,
    admin: AdminUserDep,
    settings: SettingsDep,
    session: SessionDep,
    notes: Annotated[str, Query(max_length=500)] = "",
    minimum: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """Publie l'archive footprono-apk.zip envoyée telle quelle (corps de la requête)."""
    folder = files.files_dir(settings)
    part = folder / f"apk-{secrets.token_hex(6)}.part"
    size = 0
    try:
        with part.open("wb") as out:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_APK_ARCHIVE:
                    raise AppError("archive trop volumineuse (400 Mo au plus)")
                out.write(chunk)
        if size == 0:
            raise AppError("archive vide")
        info = await asyncio.to_thread(
            app_release.publish, part, settings.app_release_dir, notes, minimum
        )
    finally:
        part.unlink(missing_ok=True)
    audit.record(session, admin, "app_release", f"version publiée : n°{info.get('build')}")
    await session.commit()
    return {"current": info}


# --- Paiements -----------------------------------------------------------------


@router.get("/payments")
async def list_payments(
    _admin: AdminUserDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Payment, User.display_name, User.phone)
            .outerjoin(User, User.id == Payment.user_id)
            .order_by(Payment.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": p.id,
            "user": name,
            "phone": phone,
            "provider": p.provider,
            "amount": p.amount,
            "currency": p.currency,
            "days": p.days,
            "status": p.status,
            "method": p.method,
            "created_at": p.created_at,
        }
        for p, name, phone in rows
    ]
