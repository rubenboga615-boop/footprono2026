"""Création et diffusion des notifications.

``add`` enregistre la notification dans la transaction en cours et la garde de
côté ; ``publish_pending`` la diffuse **après** la validation de la
transaction (canal Redis ``notifications:<utilisateur>``, relayé par le
WebSocket de l'API). Une notification n'est jamais diffusée pour une
opération annulée.

Notifications sur le téléphone fermé (Firebase Cloud Messaging) : pas encore
activées, elles demandent un projet Firebase et sa clé (phase 5).
"""

import json
import logging
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.notifications.models import Notification

logger = logging.getLogger(__name__)
_PENDING = "pending_notifications"
THIN_NBSP = "\u202f"  # espace fine insécable (milliers)
NBSP = "\u00a0"  # espace insécable (avant la devise)


def channel(user_id: int) -> str:
    return f"notifications:{user_id}"


def money(amount: int, currency: str) -> str:
    """150582, XOF → « 150 582 F CFA » (espace fine insécable entre les milliers)."""
    label = {"XOF": "F CFA", "XAF": "F CFA"}.get(currency, currency)
    return f"{amount:,}".replace(",", THIN_NBSP) + f"{NBSP}{label}"


def add(
    session: AsyncSession,
    user_id: int,
    kind: str,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> Notification:
    note = Notification(user_id=user_id, kind=kind, title=title, body=body, data=data or {})
    session.add(note)
    session.info.setdefault(_PENDING, []).append(note)
    return note


async def publish_pending(session: AsyncSession, redis: Redis | None) -> int:
    """Diffuse les notifications de la transaction validée ; renvoie leur nombre."""
    pending: list[Notification] = session.info.pop(_PENDING, [])
    if redis is None or not pending:
        return 0
    for note in pending:
        payload = {
            "id": note.id,
            "kind": note.kind,
            "title": note.title,
            "body": note.body,
            "data": note.data,
            "created_at": note.created_at.isoformat() if note.created_at else None,
        }
        try:
            await redis.publish(channel(note.user_id), json.dumps(payload, default=str))
        except Exception:  # la notification reste en base : visible à la prochaine ouverture
            logger.warning("notification_publish_failed", extra={"id": note.id})
    return len(pending)
