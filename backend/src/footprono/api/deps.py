"""Dépendances FastAPI partagées par les routes."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from footprono.accounts.models import User
from footprono.accounts.security import read_token, revoked
from footprono.accounts.service import UnauthorizedError
from footprono.core.config import Settings
from footprono.core.errors import ForbiddenError


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine = request.app.state.db_engine
    return engine


def get_redis(request: Request) -> Redis:
    client: Redis = request.app.state.redis
    return client


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
EngineDep = Annotated[AsyncEngine, Depends(get_engine)]
RedisDep = Annotated[Redis, Depends(get_redis)]


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Session en lecture pour une requête ; fermée à la fin de la requête."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Utilisateur du jeton « Authorization: Bearer … » ; 401 sinon."""
    if credentials is None:
        raise UnauthorizedError("connexion requise")
    claims = read_token(credentials.credentials, settings)
    if claims is None or claims.get("scope", "app") != "app":
        raise UnauthorizedError("session expirée ou invalide : se reconnecter")
    user = await session.get(User, claims["sub"])
    if user is None or not user.is_active or revoked(user, claims["iat"]):
        raise UnauthorizedError("session expirée ou invalide : se reconnecter")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_optional_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User | None:
    """Utilisateur connecté s'il y en a un (routes publiques : version gratuite sinon)."""
    if credentials is None:
        return None
    return await get_current_user(session, settings, credentials)


OptionalUserDep = Annotated[User | None, Depends(get_optional_user)]


def console_session_key(session_id: str) -> str:
    return f"console:session:{session_id}"


async def get_admin_user(
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Administrateur connecté à la console : jeton de la console (12 h), session
    encore ouverte (déconnexion = session effacée). Un jeton de l'application ne suffit pas."""
    if credentials is None:
        raise UnauthorizedError("connexion requise")
    claims = read_token(credentials.credentials, settings)
    if claims is None or claims.get("scope") != "console":
        raise UnauthorizedError("session de la console expirée : se reconnecter")
    owner = await redis.get(console_session_key(str(claims.get("sid"))))
    if owner is None or int(owner) != claims["sub"]:
        raise UnauthorizedError("session de la console fermée : se reconnecter")
    user = await session.get(User, claims["sub"])
    if user is None or not user.is_active or revoked(user, claims["iat"]):
        raise UnauthorizedError("session de la console expirée : se reconnecter")
    if user.role != "admin":
        raise ForbiddenError("réservé à l'administrateur")
    return user


AdminUserDep = Annotated[User, Depends(get_admin_user)]
