"""Alertes de l'administrateur sur son téléphone, par ntfy (application gratuite).

Le serveur publie sur un « canal » ntfy au nom aléatoire (généré dans la console,
gardé en base) ; l'administrateur s'y abonne dans l'application ntfy. Les alertes
ne contiennent aucune donnée personnelle (état des services, quotas, tâches).
Elles ne passent pas par l'application des joueurs.
"""

import hashlib
import logging
import re
import secrets
from typing import Any

import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.console.models import AppSetting
from footprono.core.config import Settings

logger = logging.getLogger(__name__)
TOPIC_KEY = "alerts_ntfy_topic"
# Même alerte répétée au plus une fois toutes les 12 h.
REPEAT_SECONDS = 12 * 3600
# Remplacé par les tests ; None : vrai réseau.
transport: httpx.AsyncBaseTransport | None = None


async def topic(session: AsyncSession) -> str | None:
    row = await session.get(AppSetting, TOPIC_KEY)
    return row.value if row else None


async def new_topic(session: AsyncSession) -> str:
    """Nouveau canal (l'ancien ne reçoit plus rien) ; nom long et aléatoire."""
    name = "footproba-" + secrets.token_urlsafe(18).replace("_", "").replace("-", "")[:24]
    row = await session.get(AppSetting, TOPIC_KEY)
    if row is None:
        session.add(AppSetting(key=TOPIC_KEY, value=name))
    else:
        row.value = name
    await session.flush()
    return name


async def disable(session: AsyncSession) -> None:
    row = await session.get(AppSetting, TOPIC_KEY)
    if row is not None:
        await session.delete(row)
        await session.flush()


def subscribe_url(settings: Settings, name: str) -> str:
    """Lien qui ouvre l'abonnement dans l'application ntfy."""
    host = settings.alerts_ntfy_url.removeprefix("https://").rstrip("/")
    return f"ntfy://{host}/{name}"


async def send(
    settings: Settings,
    name: str,
    title: str,
    message: str,
    *,
    priority: int = 3,
    tags: list[str] | None = None,
) -> bool:
    payload: dict[str, Any] = {
        "topic": name, "title": title[:200], "message": message[:1000],
        "priority": priority, "tags": tags or [],
    }  # fmt: skip
    try:
        async with httpx.AsyncClient(timeout=10, transport=transport) as client:
            response = await client.post(settings.alerts_ntfy_url.rstrip("/"), json=payload)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("alert_failed", extra={"error": repr(exc)})
        return False
    return True


def _key(text: str) -> str:
    # Les nombres changent (quota restant, Go libres) : même alerte quand même.
    stable = re.sub(r"\d+([.,]\d+)?", "#", text)
    return "alerts:sent:" + hashlib.sha256(stable.encode()).hexdigest()[:20]


async def send_once(
    settings: Settings,
    redis: Redis,
    name: str,
    title: str,
    message: str,
    *,
    priority: int = 3,
    tags: list[str] | None = None,
    repeat_seconds: int = REPEAT_SECONDS,
) -> bool:
    """Envoie l'alerte sauf si la même est déjà partie dans le délai donné."""
    key = _key(title + "|" + message)
    if not await redis.set(key, "1", ex=repeat_seconds, nx=True):
        return False
    sent = await send(settings, name, title, message, priority=priority, tags=tags)
    if not sent:
        await redis.delete(key)  # réessayé au prochain passage
    return sent


async def notify(
    session: AsyncSession,
    settings: Settings,
    redis: Redis,
    title: str,
    message: str,
    **options: Any,
) -> bool:
    """Alerte immédiate (tâche de la console en échec, paiement…), si le canal existe."""
    name = await topic(session)
    if name is None:
        return False
    return await send_once(settings, redis, name, title, message, **options)


async def watchdog(session: AsyncSession, redis: Redis, settings: Settings) -> dict[str, Any]:
    """Toutes les 10 minutes : la liste « à traiter » du tableau de bord et les tâches
    planifiées en échec deviennent des alertes (une fois toutes les 12 h chacune)."""
    from footprono.console import dashboard

    name = await topic(session)
    if name is None:
        return {"status": "idle", "reason": "alertes non activées"}
    board = await dashboard.dashboard(session, redis, settings)
    sent = 0
    for item in board["todo"]:
        if item["level"] == "info":
            continue
        error = item["level"] == "error"
        sent += await send_once(
            settings, redis, name,
            "FootProba : panne" if error else "FootProba : à traiter",
            item["text"], priority=5 if error else 3,
            tags=["rotating_light"] if error else ["warning"],
        )  # fmt: skip
    for task in board["runs"]:
        last = task["runs"][0] if task["runs"] else None
        if last is not None and last["status"] == "error":
            sent += await send_once(
                settings, redis, name, "FootProba : tâche en échec",
                f"« {task['label']} » a échoué ({last['at']:%d/%m %H:%M} GMT). "
                "Détails dans la console.",
                priority=4, tags=["x"], repeat_seconds=3 * 3600,
            )  # fmt: skip
    return {"status": "ok", "sent": sent}
