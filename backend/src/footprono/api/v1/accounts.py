"""Comptes : inscription, connexion, profil, portefeuille fictif."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from footprono.accounts import deletion, google, service
from footprono.accounts.models import Wallet, WalletEntry
from footprono.accounts.plans import plan_info
from footprono.accounts.schemas import (
    GoogleIn,
    GoogleRegisterIn,
    LoginIn,
    MeOut,
    PasswordIn,
    PlanOut,
    PreferencesIn,
    RegisterIn,
    TokenOut,
    WalletEntryOut,
    WalletOut,
)
from footprono.accounts.security import create_access_token
from footprono.accounts.service import UnauthorizedError
from footprono.api.deps import CurrentUserDep, RedisDep, SessionDep, SettingsDep
from footprono.core import ratelimit
from footprono.core.errors import AppError, NotFoundError

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


class GoogleUnknownError(NotFoundError):
    code = "google_account_unknown"


@router.post("/auth/google", response_model=TokenOut)
async def login_google(body: GoogleIn, session: SessionDep, settings: SettingsDep) -> TokenOut:
    """Connexion avec Google. Compte inconnu : 404 ``google_account_unknown`` avec
    l'adresse et le nom, pour l'écran « première connexion »."""
    identity = await google.verify(settings, body.id_token)
    user = await service.find_by_google(session, identity.sub)
    if user is None:
        raise GoogleUnknownError(
            "pas encore de compte FootProba pour ce compte Google",
            details={"email": identity.email, "name": identity.name},
        )
    if not user.is_active:
        raise UnauthorizedError("compte désactivé : contacte l'aide FootProba")
    return TokenOut(access_token=create_access_token(user.id, settings))


@router.post("/auth/google/register", response_model=TokenOut, status_code=201)
async def register_google(
    body: GoogleRegisterIn,
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
    identity = await google.verify(settings, body.id_token)
    user = await service.register_google(
        session, settings, identity, country=body.country, adult=body.adult
    )
    token = create_access_token(user.id, settings)
    await session.commit()
    if settings.registrations_per_ip:
        await ratelimit.hit(redis, "register-ip", ip, REGISTER_WINDOW)
    return TokenOut(access_token=token)


@router.post("/me/google", response_model=MeOut)
async def link_google(
    body: GoogleIn, user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> MeOut:
    """Lie un compte Google : connexion sans mot de passe, Premium et solde inchangés."""
    identity = await google.verify(settings, body.id_token)
    await service.link_google(session, user, identity)
    await session.commit()
    return await me(user, session)


@router.delete("/me/google", response_model=MeOut)
async def unlink_google(user: CurrentUserDep, session: SessionDep) -> MeOut:
    await service.unlink_google(session, user)
    await session.commit()
    return await me(user, session)


@router.get("/app/support")
async def support(settings: SettingsDep) -> dict[str, str | None]:
    """Aide aux joueurs (public) : numéro WhatsApp et lien direct."""
    number = settings.support_whatsapp
    digits = "".join(c for c in number or "" if c.isdigit())
    return {"whatsapp": number, "whatsapp_url": f"https://wa.me/{digits}" if digits else None}


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUserDep, session: SessionDep) -> MeOut:
    wallet = await session.get(Wallet, user.id)
    return MeOut(
        id=user.id,
        phone=user.phone,
        email=user.email,
        google_linked=user.google_sub is not None,
        has_password=bool(user.password_hash),
        display_name=user.display_name,
        country=user.country,
        currency=user.currency,
        created_at=user.created_at,
        role=user.role,
        plan=PlanOut(**plan_info(user)),
        wallet=WalletOut.model_validate(wallet),
        daily_coupons_notifications=user.daily_coupons_notifications,
    )


@router.put("/me/preferences", status_code=status.HTTP_204_NO_CONTENT)
async def set_preferences(body: PreferencesIn, user: CurrentUserDep, session: SessionDep) -> None:
    """Réglages du compte : notification quotidienne des coupons du jour."""
    user.daily_coupons_notifications = body.daily_coupons_notifications
    await session.commit()


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


@router.post("/me/password", response_model=TokenOut)
async def change_password(
    body: PasswordIn, user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> TokenOut:
    """Les autres téléphones sont déconnectés ; nouveau jeton pour celui-ci."""
    await service.change_password(session, user, body.current_password, body.new_password)
    await session.commit()
    return TokenOut(access_token=create_access_token(user.id, settings))


@router.post("/me/logout-everywhere", response_model=TokenOut)
async def logout_everywhere(
    user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> TokenOut:
    """Déconnecte tous les autres téléphones (téléphone perdu, prêté…)."""
    user.tokens_valid_after = datetime.now(UTC)
    await session.commit()
    return TokenOut(access_token=create_access_token(user.id, settings))


class DeleteIn(BaseModel):
    password: str | None = None
    # Compte créé avec Google (sans mot de passe) : nouvelle connexion Google demandée.
    google_id_token: str | None = None


class DeleteByPhoneIn(BaseModel):
    phone: str
    password: str


@router.post("/me/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    body: DeleteIn, user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> None:
    """Suppression définitive du compte (mot de passe, ou Google, redemandé)."""
    if not user.password_hash and body.google_id_token:
        identity = await google.verify(settings, body.google_id_token)
        if identity.sub != user.google_sub:
            raise UnauthorizedError("ce n'est pas le compte Google de ce compte FootProba")
        await deletion.delete_account(session, user, None)
    else:
        await deletion.delete_account(session, user, body.password or "")
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
