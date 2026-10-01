"""Comptes : inscription, connexion, profil, portefeuille fictif."""

from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from footprono.accounts import service
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
from footprono.api.deps import CurrentUserDep, SessionDep, SettingsDep

router = APIRouter(tags=["comptes"])


@router.post("/auth/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, session: SessionDep, settings: SettingsDep) -> TokenOut:
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
    return TokenOut(access_token=token)


@router.post("/auth/login", response_model=TokenOut)
async def login(body: LoginIn, session: SessionDep, settings: SettingsDep) -> TokenOut:
    user = await service.authenticate(session, body.phone, body.password)
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
