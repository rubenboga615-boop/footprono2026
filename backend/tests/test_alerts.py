"""Alertes de l'administrateur (ntfy, simulé) et sonde des tâches planifiées."""

import json
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono import alerts
from footprono.accounts import admin
from footprono.accounts import service as accounts
from footprono.console import dashboard
from footprono.console.runs import PREFIX

from .conftest import TEST_REDIS_URL, make_settings

Factory = async_sessionmaker[AsyncSession]
LOGIN = {"phone": "+2250500000055", "password": "admin-alertes-1"}


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    published: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        published.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "x"})

    monkeypatch.setattr(alerts, "transport", httpx.MockTransport(handler))
    return published


@pytest.fixture
async def redis() -> Any:
    client = Redis.from_url(TEST_REDIS_URL)
    keys = [k async for k in client.scan_iter("alerts:*")]
    if keys:
        await client.delete(*keys)
    yield client
    await client.aclose()


async def _console(client: AsyncClient, db_factory: Factory) -> dict[str, str]:
    async with db_factory() as session:
        await accounts.register(
            session, make_settings(), phone=LOGIN["phone"], password=LOGIN["password"],
            display_name="Admin", country="CI", adult=True,
        )  # fmt: skip
        await admin.set_role(session, LOGIN["phone"], "admin")
        await session.commit()
    r = await client.post("/api/v1/auth/console-login", json=LOGIN)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_alert_channel_from_the_console(
    client: AsyncClient, db_factory: Factory, sent: list[dict[str, Any]]
) -> None:
    headers = await _console(client, db_factory)
    assert (await client.get("/api/v1/admin/alerts", headers=headers)).json()["enabled"] is False
    assert (await client.post("/api/v1/admin/alerts/test", headers=headers)).status_code == 400

    info = (await client.post("/api/v1/admin/alerts/setup", headers=headers)).json()
    topic = info["topic"]
    assert topic.startswith("footproba-")
    assert len(topic) >= 30
    assert info["subscribe_url"] == f"ntfy://ntfy.sh/{topic}"
    assert (await client.post("/api/v1/admin/alerts/test", headers=headers)).json() == {
        "sent": True
    }
    assert sent[-1]["topic"] == topic
    assert sent[-1]["title"] == "FootProba : alerte d'essai"

    other = (await client.post("/api/v1/admin/alerts/setup", headers=headers)).json()["topic"]
    assert other != topic  # nouveau canal : l'ancien ne reçoit plus rien
    assert (await client.delete("/api/v1/admin/alerts", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/admin/alerts", headers=headers)).json()["topic"] is None


async def test_watchdog_sends_each_problem_once(
    db_factory: Factory,
    sent: list[dict[str, Any]],
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings()
    async with db_factory() as session:
        assert (await alerts.watchdog(session, redis, settings))["status"] == "idle"
        await alerts.new_topic(session)
        await session.commit()

    board: dict[str, Any] = {
        "todo": [
            {"level": "error", "text": "aucun worker Celery ne répond : tâches à l'arrêt"},
            {"level": "warning", "text": "plus que 420 requêtes API-Football aujourd'hui"},
            {"level": "info", "text": "1 paiement(s) en attente de confirmation"},
        ],
        "runs": [
            {
                "task": "collect_odds", "label": "Cotes (3 h)",
                "runs": [{"at": datetime(2026, 10, 5, 7, 30, tzinfo=UTC), "status": "error",
                          "error": "HTTPError : 429 Too Many Requests"}],
            },
        ],
    }  # fmt: skip

    async def fake_dashboard(*_: Any) -> dict[str, Any]:
        return board

    monkeypatch.setattr(dashboard, "dashboard", fake_dashboard)
    async with db_factory() as session:
        result = await alerts.watchdog(session, redis, settings)
    assert result == {"status": "ok", "sent": 3}  # l'information n'est pas une alerte
    assert [m["priority"] for m in sent] == [5, 3, 4]
    assert "Cotes (3 h)" in sent[2]["message"]
    assert "Cause : HTTPError : 429 Too Many Requests." in sent[2]["message"]

    # Dix minutes plus tard, le quota a encore baissé : même alerte, pas renvoyée.
    board["todo"][1]["text"] = "plus que 380 requêtes API-Football aujourd'hui"
    async with db_factory() as session:
        assert (await alerts.watchdog(session, redis, settings))["sent"] == 0


async def test_tasks_probe_for_external_monitoring(client: AsyncClient) -> None:
    store = Redis.from_url(TEST_REDIS_URL)
    try:
        await store.delete(PREFIX + "follow_live")
        stopped = await client.get("/api/v1/health/tasks")
        assert (stopped.status_code, stopped.json()["status"]) == (503, "stopped")
        await store.lpush(
            PREFIX + "follow_live", json.dumps({"at": time.time(), "s": 1, "st": "ok"})
        )
        alive = await client.get("/api/v1/health/tasks")
        assert (alive.status_code, alive.json()["status"]) == (200, "ok")
    finally:
        await store.delete(PREFIX + "follow_live")
        await store.aclose()
