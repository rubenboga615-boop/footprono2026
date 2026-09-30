"""Dépendances FastAPI partagées par les routes."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from footprono.accounts.models import User
from footprono.accounts.security import read_access_token
from footprono.accounts.service import UnauthorizedError
from footprono.core.config import Settings


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
    user_id = read_access_token(credentials.credentials, settings)
    user = await session.get(User, user_id) if user_id is not None else None
    if user is None or not user.is_active:
        raise UnauthorizedError("session expirée ou invalide : se reconnecter")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
