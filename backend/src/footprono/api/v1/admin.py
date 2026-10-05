"""Administration : comptes, Premium (activation manuelle avant Mobile Money), statistiques."""

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from footprono.accounts import admin
from footprono.accounts.plans import plan_info
from footprono.api.deps import AdminUserDep, SessionDep, SettingsDep
from footprono.bookmaker import smart_coupon
from footprono.core.errors import AppError
from footprono.notifications import push

router = APIRouter(prefix="/admin", tags=["administration"])


class AdminUserOut(BaseModel):
    id: int
    phone: str
    display_name: str
    country: str
    role: str
    is_active: bool
    created_at: datetime
    plan: str
    premium_until: datetime | None


class SubscriptionEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    days: int
    premium_until: datetime
    admin_id: int | None
    note: str | None
    created_at: datetime


class GrantIn(BaseModel):
    days: int = Field(30, ge=1, le=admin.MAX_GRANT_DAYS)
    note: str | None = Field(None, max_length=200, examples=["paiement Mobile Money reçu"])


class RevokeIn(BaseModel):
    note: str | None = Field(None, max_length=200)


class ActiveIn(BaseModel):
    active: bool


def _out(user: Any) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        phone=user.phone,
        display_name=user.display_name,
        country=user.country,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        plan=plan_info(user)["name"],
        premium_until=user.premium_until,
    )


@router.get("/stats")
async def admin_stats(
    _: AdminUserDep, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    return {**await admin.stats(session), "push": push.status(settings)}


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    _: AdminUserDep,
    session: SessionDep,
    q: Annotated[str | None, Query(description="nom ou numéro")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminUserOut]:
    return [_out(u) for u in await admin.search_users(session, q, limit=limit, offset=offset)]


@router.get("/users/{user_id}")
async def get_user(user_id: int, _: AdminUserDep, session: SessionDep) -> dict[str, Any]:
    user = await admin.get_user(session, user_id)
    history = await admin.subscription_history(session, user_id)
    return {
        "user": _out(user),
        "subscription_events": [SubscriptionEventOut.model_validate(e) for e in history],
    }


@router.post("/users/{user_id}/premium", response_model=AdminUserOut)
async def grant_premium(
    user_id: int, body: GrantIn, me: AdminUserDep, session: SessionDep
) -> AdminUserOut:
    user = await admin.get_user(session, user_id)
    await admin.grant_premium(session, me, user, body.days, note=body.note)
    await session.commit()
    return _out(user)


@router.post("/users/{user_id}/premium/revoke", response_model=AdminUserOut)
async def revoke_premium(
    user_id: int, body: RevokeIn, me: AdminUserDep, session: SessionDep
) -> AdminUserOut:
    user = await admin.get_user(session, user_id)
    await admin.revoke_premium(session, me, user, note=body.note)
    await session.commit()
    return _out(user)


@router.post("/users/{user_id}/active", response_model=AdminUserOut)
async def set_active(
    user_id: int, body: ActiveIn, me: AdminUserDep, session: SessionDep
) -> AdminUserOut:
    user = await admin.get_user(session, user_id)
    await admin.set_active(session, me, user, body.active)
    await session.commit()
    return _out(user)


class BookingCodeIn(BaseModel):
    bookmaker: str = Field("1xbet", examples=["1xbet"])
    code: str = Field(..., max_length=32, description="vide pour retirer le code")


@router.get("/smart-coupons")
async def admin_smart_coupons(
    _: AdminUserDep, session: SessionDep, day: date | None = None
) -> dict[str, Any]:
    """Coupons du jour à recréer chez le bookmaker, avec les codes déjà saisis."""
    return await smart_coupon.day_coupons(session, day)


@router.put("/smart-coupons/{coupon_id}/booking-code")
async def set_booking_code(
    coupon_id: int, body: BookingCodeIn, _: AdminUserDep, session: SessionDep
) -> dict[str, Any]:
    return await smart_coupon.set_booking_code(session, coupon_id, body.bookmaker, body.code)


class RoleIn(BaseModel):
    role: str = Field(pattern="^(user|admin)$")


class PhoneIn(BaseModel):
    phone: str = Field(max_length=24)


@router.post("/users/{user_id}/role", response_model=AdminUserOut)
async def set_user_role(
    user_id: int, body: RoleIn, me: AdminUserDep, session: SessionDep
) -> AdminUserOut:
    """Nommer ou retirer un administrateur (jamais soi-même : pas de console sans admin)."""
    user = await admin.get_user(session, user_id)
    if user.id == me.id and body.role != "admin":
        raise AppError("impossible de retirer ton propre rôle d'administrateur")
    await admin.set_role(session, user.phone, body.role)
    await session.commit()
    return _out(user)


@router.post("/users/{user_id}/phone", response_model=AdminUserOut)
async def set_user_phone(
    user_id: int, body: PhoneIn, _: AdminUserDep, session: SessionDep
) -> AdminUserOut:
    user = await admin.get_user(session, user_id)
    await admin.change_phone(session, user.phone, body.phone)
    await session.commit()
    return _out(user)


@router.post("/users/{user_id}/password-reset")
async def reset_user_password(user_id: int, _: AdminUserDep, session: SessionDep) -> dict[str, str]:
    """Mot de passe provisoire, affiché une seule fois (jamais enregistré en clair)."""
    user = await admin.get_user(session, user_id)
    _, password = await admin.reset_password(session, user.phone)
    await session.commit()
    return {"password": password}
