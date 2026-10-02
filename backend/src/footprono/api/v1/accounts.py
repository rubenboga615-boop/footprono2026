"""Comptes : inscription, connexion, profil, portefeuille fictif."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from footprono.accounts import deletion, service
from footprono.accounts.models import Wallet, WalletEntry
from footprono.accounts.plans import plan_info
from footprono.accounts.schemas import (
    LoginIn,
    MeOut,
    PasswordIn,
    PlanOut,
    RegisterIn,
    TokenOut,
    WalletEntryOut,
    WalletOut,
)
from footprono.accounts.security import create_access_token
from footprono.accounts.service import UnauthorizedError
from footprono.api.deps import CurrentUserDep, RedisDep, SessionDep, SettingsDep
from footprono.core import ratelimit
from footprono.core.errors import AppError

router = APIRouter(tags=["comptes"])


LOGIN_WINDOW = 15 * 60
REGISTER_WINDOW = 60 * 60


def _client_ip(request: Request) -> str:
    # Derrière Caddy, uvicorn (--proxy-headers) remplace l'adresse par celle du client.
    return request.client.host if request.client else "inconnue"


@router.post("/auth/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterIn,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisDep,
) -> TokenOut:
    ip = _client_ip(request)
    if settings.registrations_per_ip:
        await ratelimit.check(
            redis, "register-ip", ip, settings.registrations_per_ip, REGISTER_WINDOW
        )
    user = await service.register(
        session,
        settings,
        phone=body.phone,
        password=body.password,
        display_name=body.display_name,
        country=body.country,
        adult=body.adult,
    )
    token = create_access_token(user.id, settings)
    await session.commit()
    if settings.registrations_per_ip:
        await ratelimit.hit(redis, "register-ip", ip, REGISTER_WINDOW)
    return TokenOut(access_token=token)


@router.post("/auth/login", response_model=TokenOut)
async def login(
    body: LoginIn,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisDep,
) -> TokenOut:
    """Trop d'échecs pour un numéro (ou une adresse) : connexion refusée 15 minutes."""
    ip = _client_ip(request)
    try:  # « +229 97… » et « +22997… » : un seul compteur
        phone = service.normalize_phone(body.phone)
    except AppError:
        phone = body.phone.strip()
    limits = [
        ("login-phone", phone, settings.login_failures_per_phone),
        ("login-ip", ip, settings.login_failures_per_ip),
    ]
    for scope, ident, limit in limits:
        if limit:
            await ratelimit.check(redis, scope, ident, limit, LOGIN_WINDOW)
    try:
        user = await service.authenticate(session, body.phone, body.password)
    except UnauthorizedError:
        for scope, ident, limit in limits:
            if limit:
                await ratelimit.hit(redis, scope, ident, LOGIN_WINDOW)
        raise
    return TokenOut(access_token=create_access_token(user.id, settings))


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUserDep, session: SessionDep) -> MeOut:
    wallet = await session.get(Wallet, user.id)
    return MeOut(
        id=user.id,
        phone=user.phone,
        display_name=user.display_name,
        country=user.country,
        currency=user.currency,
        created_at=user.created_at,
        role=user.role,
        plan=PlanOut(**plan_info(user)),
        wallet=WalletOut.model_validate(wallet),
    )


@router.get("/me/wallet/entries", response_model=list[WalletEntryOut])
async def wallet_entries(
    user: CurrentUserDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[WalletEntry]:
    rows = await session.scalars(
        select(WalletEntry)
        .where(WalletEntry.user_id == user.id)
        .order_by(WalletEntry.id.desc())
        .limit(limit)
    )
    return list(rows.all())


@router.post("/me/wallet/refill", response_model=WalletEntryOut)
async def refill(user: CurrentUserDep, session: SessionDep, settings: SettingsDep) -> WalletEntry:
    entry = await service.refill(session, settings, user.id)
    await session.commit()
    return entry


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: PasswordIn, user: CurrentUserDep, session: SessionDep) -> None:
    await service.change_password(session, user, body.current_password, body.new_password)
    await session.commit()


class DeleteIn(BaseModel):
    password: str


class DeleteByPhoneIn(BaseModel):
    phone: str
    password: str


@router.post("/me/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(body: DeleteIn, user: CurrentUserDep, session: SessionDep) -> None:
    """Suppression définitive du compte (mot de passe redemandé)."""
    await deletion.delete_account(session, user, body.password)
    await session.commit()


@router.post("/account/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_by_phone(
    body: DeleteByPhoneIn,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisDep,
) -> None:
    """Même suppression sans l'application (page web /suppression-compte), mêmes limites
    de tentatives que la connexion."""
    ip = _client_ip(request)
    try:
        phone = service.normalize_phone(body.phone)
    except AppError:
        phone = body.phone.strip()
    limits = [
        ("login-phone", phone, settings.login_failures_per_phone),
        ("login-ip", ip, settings.login_failures_per_ip),
    ]
    for scope, ident, limit in limits:
        if limit:
            await ratelimit.check(redis, scope, ident, limit, LOGIN_WINDOW)
    try:
        user = await service.authenticate(session, body.phone, body.password)
    except UnauthorizedError:
        for scope, ident, limit in limits:
            if limit:
                await ratelimit.hit(redis, scope, ident, LOGIN_WINDOW)
        raise
    await deletion.delete_account(session, user, body.password)
    await session.commit()
