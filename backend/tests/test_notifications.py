"""Notifications : créées au règlement, lues par l'API, reçues en direct (WebSocket)."""

import asyncio
import json
from typing import Any

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from footprono.accounts.security import create_access_token
from footprono.bookmaker.settlement import settle_bets
from footprono.football.models import Match, MatchStatus
from footprono.main import create_app
from footprono.notifications.service import channel, money

from .conftest import TEST_REDIS_URL, make_settings
from .test_bets import _login, _sel, world  # noqa: F401 (fixture partagée)

Factory = async_sessionmaker[AsyncSession]


def test_money_format() -> None:
    assert money(150_582, "XOF") == "150\u202f582\u00a0F CFA"
    assert money(500, "XOF") == "500\u00a0F CFA"


async def _finish(factory: Factory, match_id: int, home: int, away: int) -> None:
    async with factory() as session:
        await session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(
                status=MatchStatus.FINISHED, home_goals=home, away_goals=away,
                result_source="api_football", api_status="FT",
            )
        )  # fmt: skip
        await session.commit()


async def test_settlement_notifies_and_publishes(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    headers = await _login(client)
    await client.post(
        "/api/v1/bets",
        json={"stake": 2_000, "selections": [_sel(world["m1"], "1X2", "home")]},
        headers=headers,
    )
    redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel(world["user_id"]))
    await _finish(db_factory, world["m1"], 3, 1)
    async with db_factory() as session:
        report = await settle_bets(session, redis=redis)
    assert report["notified"] == 1

    received = None
    for _ in range(20):
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
        if message:
            received = json.loads(message["data"])
            break
    await pubsub.aclose()
    await redis.aclose()
    assert received is not None
    assert received["title"] == "Pari gagné"
    assert "3\u202f700\u00a0F CFA" in received["body"]  # 2 000 x 1,85
    # Le match, pas un numéro interne : « Équipe A - Équipe B : 3 700 F CFA crédités… »
    assert " - " in received["body"]
    assert "n°" not in received["body"]

    listed = (await client.get("/api/v1/me/notifications?unread=true", headers=headers)).json()
    assert [n["kind"] for n in listed] == ["bet_settled"]
    read = await client.post(f"/api/v1/me/notifications/{listed[0]['id']}/read", headers=headers)
    assert read.json()["read_at"] is not None
    assert (await client.get("/api/v1/me/notifications?unread=true", headers=headers)).json() == []


def test_websocket_requires_a_valid_token() -> None:
    with (
        TestClient(create_app(make_settings())) as http,
        pytest.raises(WebSocketDisconnect) as closed,
        http.websocket_connect("/api/v1/ws?token=faux") as ws,
    ):
        ws.receive_text()
    assert closed.value.code == 1008


async def test_websocket_relays_published_notifications(
    world: dict[str, Any],  # noqa: F811
) -> None:
    settings = make_settings()
    token = create_access_token(world["user_id"], settings)

    def run() -> dict[str, Any]:
        async def publish() -> None:
            r = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
            await r.publish(channel(world["user_id"]), json.dumps({"title": "Test"}))
            await r.aclose()

        with (
            TestClient(create_app(settings)) as http,
            http.websocket_connect(f"/api/v1/ws?token={token}") as ws,
        ):
            ws.send_text("ping")
            assert json.loads(ws.receive_text()) == {"type": "pong"}
            asyncio.run(publish())
            return dict(json.loads(ws.receive_text()))

    assert (await asyncio.to_thread(run)) == {"title": "Test"}


def test_uvicorn_has_a_websocket_implementation() -> None:
    """Sans wsproto (ou websockets), uvicorn répond 404 au WebSocket /ws."""
    import importlib.util

    assert importlib.util.find_spec("wsproto") or importlib.util.find_spec("websockets")
