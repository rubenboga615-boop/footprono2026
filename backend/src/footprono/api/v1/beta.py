"""Mode bêta : interrupteur du joueur, envoi des événements, Observatoire de la console.

Partage volontaire, anonyme et temporaire (``FP_BETA_SHARING``) ; voir ``footprono.beta``.
"""

from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from footprono.accounts import audit
from footprono.api.deps import AdminUserDep, CurrentUserDep, SessionDep, SettingsDep
from footprono.beta import service
from footprono.core.errors import AppError

router = APIRouter(tags=["bêta"])


class BetaClosedError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "beta_closed"


class BetaIn(BaseModel):
    enabled: bool


class EventIn(BaseModel):
    kind: str = Field(max_length=16)
    path: str = Field(default="", max_length=512)
    duration_ms: int | None = Field(default=None, ge=0, le=600_000)
    detail: str | None = Field(default=None, max_length=500)


class EventsIn(BaseModel):
    events: list[EventIn] = Field(max_length=service.MAX_EVENTS)


@router.put("/me/beta")
async def set_beta(
    body: BetaIn, user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    """Allume (période de test ouverte seulement) ou éteint le partage."""
    if body.enabled and not settings.beta_sharing:
        raise BetaClosedError("la période de test est terminée : plus rien n'est partagé")
    return await service.set_sharing(session, user, body.enabled)


@router.post("/me/beta/events")
async def beta_events(
    body: EventsIn, user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> dict[str, int]:
    """Événements de l'application d'un testeur volontaire ; ignorés sinon."""
    if not settings.beta_sharing:
        return {"kept": 0}
    events = [e.model_dump() for e in body.events]
    return {"kept": await service.record(session, user, events)}


@router.get("/admin/console/beta", tags=["console"])
async def observatory(
    _admin: AdminUserDep, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    return {"enabled": settings.beta_sharing, **await service.observatory(session)}


@router.get("/admin/console/beta/export", tags=["console"])
async def export(admin: AdminUserDep, session: SessionDep) -> dict[str, Any]:
    """Export sans données personnelles (numéros de testeur uniquement)."""
    data = await service.export(session)
    audit.record(
        session, admin, "beta_export", "export de l'Observatoire (sans données personnelles)"
    )
    await session.commit()
    return data


@router.delete("/admin/console/beta")
async def erase(admin: AdminUserDep, session: SessionDep) -> dict[str, int]:
    """Fin de la période de test : tout est effacé."""
    removed = await service.erase(session)
    audit.record(
        session, admin, "beta_erase",
        f"mode bêta effacé : {removed['events']} événements, {removed['testers']} testeurs",
    )  # fmt: skip
    await session.commit()
    return removed
