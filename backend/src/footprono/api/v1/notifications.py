"""Notifications : liste, lecture, et diffusion en direct par WebSocket.

WebSocket : ``/api/v1/ws?token=<jeton d'accès>``. Chaque notification créée
pour l'utilisateur (pari réglé, palier de montante, score corrigé…) est
envoyée en JSON dès que le règlement est validé.
"""

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from footprono.accounts.models import User
from footprono.accounts.security import read_token, revoked
from footprono.api.deps import CurrentUserDep, SessionDep
from footprono.core.config import Settings
from footprono.core.errors import NotFoundError
from footprono.notifications.models import Notification, PushDevice
from footprono.notifications.service import channel

router = APIRouter(tags=["notifications"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    body: str
    data: dict[str, object]
    created_at: datetime
    read_at: datetime | None


@router.get("/me/notifications", response_model=list[NotificationOut])
async def list_notifications(
    user: CurrentUserDep,
    session: SessionDep,
    unread: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = await session.scalars(stmt.order_by(Notification.id.desc()).limit(limit))
    return list(rows.all())


@router.post("/me/notifications/{notification_id}/read", response_model=NotificationOut)
async def mark_read(
    notification_id: int, user: CurrentUserDep, session: SessionDep
) -> Notification:
    note = await session.get(Notification, notification_id)
    if note is None or note.user_id != user.id:
        raise NotFoundError(f"notification {notification_id} introuvable")
    note.read_at = note.read_at or datetime.now(UTC)
    await session.commit()
    return note


@router.post("/me/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(user: CurrentUserDep, session: SessionDep) -> None:
    await session.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await session.commit()


class DeviceIn(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    platform: str = Field(default="android", pattern="^(android|ios|web)$")


class DeviceTokenIn(BaseModel):
    token: str = Field(min_length=1, max_length=512)


@router.post("/me/devices", status_code=status.HTTP_204_NO_CONTENT)
async def register_device(body: DeviceIn, user: CurrentUserDep, session: SessionDep) -> None:
    """Enregistre le téléphone (jeton Firebase) pour les notifications push.

    Un jeton déjà connu passe au compte connecté : un téléphone ne reçoit que les
    notifications du compte ouvert dessus.
    """
    device = await session.scalar(select(PushDevice).where(PushDevice.token == body.token))
    if device is None:
        session.add(PushDevice(user_id=user.id, token=body.token, platform=body.platform))
    else:
        device.user_id, device.platform = user.id, body.platform
        device.last_seen_at = datetime.now(UTC)
    await session.commit()


@router.post("/me/devices/remove", status_code=status.HTTP_204_NO_CONTENT)
async def remove_device(body: DeviceTokenIn, user: CurrentUserDep, session: SessionDep) -> None:
    """Déconnexion : le téléphone ne reçoit plus les notifications de ce compte."""
    await session.execute(
        delete(PushDevice).where(PushDevice.token == body.token, PushDevice.user_id == user.id)
    )
    await session.commit()


@router.websocket("/ws")
async def notifications_socket(websocket: WebSocket, token: str = "") -> None:
    settings: Settings = websocket.app.state.settings
    factory: async_sessionmaker = websocket.app.state.session_factory  # type: ignore[type-arg]
    claims = read_token(token, settings) if token else None
    user_id: int | None = None
    if claims is not None and claims.get("scope", "app") == "app":
        async with factory() as session:
            user = await session.get(User, claims["sub"])
        if user is not None and user.is_active and not revoked(user, claims["iat"]):
            user_id = user.id
    if user_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="connexion requise")
        return
    await websocket.accept()
    # Connexion Redis dédiée, sans délai de lecture : elle attend les messages.
    redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel(user_id))

    async def forward() -> None:
        async for message in pubsub.listen():
            if message.get("type") == "message":
                await websocket.send_text(str(message["data"]))

    task = asyncio.create_task(forward())
    try:
        while True:  # garde la connexion ; le client peut envoyer « ping »
            if await websocket.receive_text() == "ping":
                await websocket.send_text('{"type": "pong"}')
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        await pubsub.unsubscribe()
        await pubsub.aclose()
        await redis.aclose()
