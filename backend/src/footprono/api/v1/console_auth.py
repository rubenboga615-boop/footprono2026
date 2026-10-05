"""Connexion à la console : numéro, mot de passe et code de sécurité à 6 chiffres.

La console a ses propres sessions (12 heures, enregistrées dans Redis) : se
déconnecter efface la session, « Déconnecter toutes mes sessions » les efface
toutes. Un jeton de l'application des joueurs (30 jours) n'ouvre pas la console.
"""

import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from footprono.accounts import audit, service, totp
from footprono.accounts.models import User
from footprono.accounts.security import CONSOLE_HOURS, create_access_token, read_token
from footprono.accounts.service import UnauthorizedError
from footprono.api.deps import (
    AdminUserDep,
    RedisDep,
    SessionDep,
    SettingsDep,
    _bearer,
    console_session_key,
)
from footprono.api.v1.accounts import LOGIN_WINDOW, _client_ip
from footprono.core import ratelimit
from footprono.core.config import Settings
from footprono.core.errors import AppError, ForbiddenError

router = APIRouter(tags=["console"])

SESSION_SECONDS = CONSOLE_HOURS * 3600
PENDING_SECONDS = 10 * 60


class TotpRequiredError(UnauthorizedError):
    code = "totp_required"


class ConsoleLoginIn(BaseModel):
    phone: str
    password: str
    code: str | None = Field(None, max_length=12, description="code à 6 chiffres, si activé")


class CodeIn(BaseModel):
    code: str = Field(max_length=12)


def _sessions_key(user_id: int) -> str:
    return f"console:sessions:{user_id}"


async def _open_session(redis: Redis, user_id: int) -> str:
    sid = secrets.token_urlsafe(18)
    await redis.set(console_session_key(sid), str(user_id), ex=SESSION_SECONDS)
    await redis.sadd(_sessions_key(user_id), sid)  # type: ignore[misc]
    await redis.expire(_sessions_key(user_id), SESSION_SECONDS)
    return sid


async def _open_sessions(redis: Redis, user_id: int) -> list[str]:
    sids = [
        s.decode() if isinstance(s, bytes) else str(s)
        for s in await redis.smembers(_sessions_key(user_id))  # type: ignore[misc]
    ]
    alive = [sid for sid in sids if await redis.exists(console_session_key(sid))]
    stale = set(sids) - set(alive)
    if stale:
        await redis.srem(_sessions_key(user_id), *stale)  # type: ignore[misc]
    return alive


async def check_code(redis: Redis, settings: Settings, user: User, code: str) -> bool:
    """Code juste et jamais utilisé (un code vu une fois est refusé ensuite)."""
    secret = totp.unseal(settings, user.totp_secret or "")
    counter = totp.matching_counter(secret, code) if secret else None
    if counter is None:
        return False
    last = await redis.get(f"console:totp-last:{user.id}")
    if last is not None and counter <= int(last):
        return False
    await redis.set(f"console:totp-last:{user.id}", str(counter), ex=300)
    return True


@router.post("/auth/console-login")
async def console_login(
    body: ConsoleLoginIn,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisDep,
) -> dict[str, Any]:
    """Code demandé seulement après un numéro et un mot de passe justes
    (401 ``totp_required``). Mêmes limites de tentatives que la connexion."""
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

    async def failed() -> None:
        for scope, ident, limit in limits:
            if limit:
                await ratelimit.hit(redis, scope, ident, LOGIN_WINDOW)

    try:
        user = await service.authenticate(session, body.phone, body.password)
    except UnauthorizedError:
        await failed()
        raise
    if user.role != "admin":
        raise ForbiddenError("ce compte n'est pas administrateur")
    if user.totp_secret:
        if not body.code:
            raise TotpRequiredError("code de sécurité demandé")
        if not await check_code(redis, settings, user, body.code):
            await failed()
            audit.record(session, user, "console_code_refused", "code de sécurité refusé", user)
            await session.commit()
            raise UnauthorizedError("code incorrect ou déjà utilisé : attends le suivant")
    sid = await _open_session(redis, user.id)
    audit.record(session, user, "console_login", "connexion à la console", user)
    await session.commit()
    return {
        "access_token": create_access_token(user.id, settings, console_session=sid),
        "token_type": "bearer",
        "expires_in": SESSION_SECONDS,
    }


@router.get("/admin/console/me")
async def console_me(admin: AdminUserDep) -> dict[str, Any]:
    return {
        "id": admin.id,
        "display_name": admin.display_name,
        "role": admin.role,
        "totp_enabled": admin.totp_secret is not None,
    }


@router.post("/admin/console/logout", status_code=status.HTTP_204_NO_CONTENT)
async def console_logout(
    admin: AdminUserDep,
    settings: SettingsDep,
    redis: RedisDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    claims = read_token(credentials.credentials, settings) if credentials else None
    if claims:
        sid = str(claims.get("sid"))
        await redis.delete(console_session_key(sid))
        await redis.srem(_sessions_key(admin.id), sid)  # type: ignore[misc]


@router.post("/admin/console/logout-all")
async def console_logout_all(
    admin: AdminUserDep, session: SessionDep, redis: RedisDep
) -> dict[str, int]:
    """Ferme toutes les sessions de la console de ce compte (celle-ci comprise)."""
    sids = await _open_sessions(redis, admin.id)
    for sid in sids:
        await redis.delete(console_session_key(sid))
    await redis.delete(_sessions_key(admin.id))
    audit.record(session, admin, "console_logout_all", f"{len(sids)} session(s) fermée(s)", admin)
    await session.commit()
    return {"closed": len(sids)}


@router.get("/admin/security")
async def security_status(admin: AdminUserDep, redis: RedisDep) -> dict[str, Any]:
    return {
        "totp_enabled": admin.totp_secret is not None,
        "sessions": len(await _open_sessions(redis, admin.id)),
        "session_hours": CONSOLE_HOURS,
    }


@router.post("/admin/security/totp/setup")
async def totp_setup(admin: AdminUserDep, settings: SettingsDep, redis: RedisDep) -> dict[str, str]:
    """Nouvelle clé, à ajouter dans l'application d'authentification ; activée
    seulement quand un code juste est saisi (``/enable``), dans les 10 minutes."""
    if admin.totp_secret:
        raise AppError("le code de sécurité est déjà activé")
    secret = totp.new_secret()
    await redis.set(
        f"console:totp-pending:{admin.id}", totp.seal(settings, secret), ex=PENDING_SECONDS
    )
    account = admin.phone or admin.email or admin.display_name
    return {"secret": secret, "uri": totp.uri(secret, account)}


@router.post("/admin/security/totp/enable")
async def totp_enable(
    body: CodeIn, admin: AdminUserDep, session: SessionDep, settings: SettingsDep, redis: RedisDep
) -> dict[str, bool]:
    sealed = await redis.get(f"console:totp-pending:{admin.id}")
    secret = totp.unseal(settings, sealed.decode() if isinstance(sealed, bytes) else sealed or "")
    if secret is None:
        raise AppError("clé expirée : recommence l'activation")
    if totp.matching_counter(secret, body.code) is None:
        raise AppError("code incorrect : vérifie l'heure du téléphone et réessaie")
    admin.totp_secret = totp.seal(settings, secret)
    await redis.delete(f"console:totp-pending:{admin.id}")
    audit.record(session, admin, "totp_enabled", "code de sécurité activé", admin)
    await session.commit()
    return {"totp_enabled": True}


@router.post("/admin/security/totp/disable")
async def totp_disable(
    body: CodeIn, admin: AdminUserDep, session: SessionDep, settings: SettingsDep, redis: RedisDep
) -> dict[str, bool]:
    """Désactivation : un code juste est demandé (téléphone toujours en main)."""
    if not admin.totp_secret:
        return {"totp_enabled": False}
    if not await check_code(redis, settings, admin, body.code):
        raise AppError("code incorrect ou déjà utilisé")
    admin.totp_secret = None
    audit.record(session, admin, "totp_disabled", "code de sécurité désactivé", admin)
    await session.commit()
    return {"totp_enabled": False}


@router.get("/admin/console/audit")
async def admin_audit(
    _admin: AdminUserDep, session: SessionDep, limit: int = Query(200, ge=1, le=500)
) -> list[dict[str, Any]]:
    """Journal des actions d'administration, de la plus récente à la plus ancienne."""
    return await audit.recent(session, limit)
