"""Formules gratuite / Premium et administration (phase 5)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.accounts import admin
from footprono.accounts import service as accounts
from footprono.accounts.models import User
from footprono.core.errors import AppError

from .conftest import make_settings
from .test_bets import NOW, _login, _sel, quote, world  # noqa: F401 (fixture)

Factory = async_sessionmaker[AsyncSession]


async def _add_double_chance(db_factory: Factory, match_id: int) -> None:
    async with db_factory() as session:
        session.add(
            quote(match_id, "1xBet", "Double Chance", "Home/Draw", "1.25", NOW - timedelta(hours=1))
        )
        await session.commit()


async def _end_premium(db_factory: Factory, user_id: int) -> None:
    async with db_factory() as session:
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(premium_until=datetime.now(UTC) - timedelta(minutes=1))
        )
        await session.commit()


async def test_trial_then_free_plan(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    m1 = world["m1"]
    await _add_double_chance(db_factory, m1)
    headers = await _login(client)

    me = (await client.get("/api/v1/me", headers=headers)).json()
    assert me["plan"]["name"] == "premium"  # 7 jours offerts à l'inscription
    assert me["plan"]["days_left"] in (6, 7)
    assert me["plan"]["premium_price"] == 2000
    assert me["role"] == "user"

    def markets(offer: list[dict[str, Any]]) -> set[str]:
        return {o["market"] for o in offer}

    anonymous = (await client.get(f"/api/v1/matches/{m1}/offer")).json()
    assert markets(anonymous) == {"1X2", "OU"}
    trial = (await client.get(f"/api/v1/matches/{m1}/offer", headers=headers)).json()
    assert "DC" in markets(trial)

    await _end_premium(db_factory, world["user_id"])
    me = (await client.get("/api/v1/me", headers=headers)).json()
    assert me["plan"]["name"] == "free"
    free = (await client.get(f"/api/v1/matches/{m1}/offer", headers=headers)).json()
    assert "DC" not in markets(free)

    refused = await client.post(
        "/api/v1/bets",
        headers=headers,
        json={"stake": 1000, "selections": [_sel(m1, "DC", "1X")]},
    )
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "premium_required"
    # un combiné est refusé en entier dès qu'une sélection est Premium
    combo = await client.post(
        "/api/v1/bets",
        headers=headers,
        json={
            "stake": 1000,
            "selections": [_sel(world["m2"], "1X2", "home"), _sel(m1, "DC", "1X")],
        },
    )
    assert combo.status_code == 403
    allowed = await client.post(
        "/api/v1/bets",
        headers=headers,
        json={"stake": 1000, "selections": [_sel(m1, "1X2", "home")]},
    )
    assert allowed.status_code == 201, allowed.text

    suggestions = await client.get("/api/v1/montantes/1/suggestions", headers=headers)
    assert suggestions.status_code == 403
    assert suggestions.json()["error"]["code"] == "premium_required"


async def test_admin_grants_and_revokes_premium(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    player = await _login(client)
    assert (await client.get("/api/v1/admin/stats", headers=player)).status_code == 401

    async with db_factory() as session:
        boss = await accounts.register(
            session, make_settings(), phone="+22997222222", password="87654321",
            display_name="Admin", country="BJ", adult=True,
        )  # fmt: skip
        await admin.set_role(session, "+229 97 22 22 22", "admin")
        await session.commit()
        boss_id = boss.id
    r = await client.post(
        "/api/v1/auth/console-login", json={"phone": "+22997222222", "password": "87654321"}
    )
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    found = (await client.get("/api/v1/admin/users", params={"q": "Kofi"}, headers=headers)).json()
    assert [u["id"] for u in found] == [world["user_id"]]
    by_phone = await client.get("/api/v1/admin/users", params={"q": "97111"}, headers=headers)
    assert [u["id"] for u in by_phone.json()] == [world["user_id"]]

    uid = world["user_id"]
    trial_end = datetime.fromisoformat(found[0]["premium_until"])
    granted = await client.post(
        f"/api/v1/admin/users/{uid}/premium",
        json={"days": 30, "note": "paiement reçu"},
        headers=headers,
    )
    assert granted.status_code == 200, granted.text
    # la période accordée s'ajoute à l'essai en cours
    assert datetime.fromisoformat(granted.json()["premium_until"]) - trial_end == timedelta(days=30)

    detail = (await client.get(f"/api/v1/admin/users/{uid}", headers=headers)).json()
    events = detail["subscription_events"]
    assert [e["kind"] for e in events] == ["admin_grant", "trial"]
    assert events[0]["admin_id"] == boss_id

    stats = (await client.get("/api/v1/admin/stats", headers=headers)).json()
    assert stats["users"] == 2
    assert stats["premium"] == 2
    assert stats["premium_trial"] == 1  # l'administrateur est encore en essai

    revoked = await client.post(
        f"/api/v1/admin/users/{uid}/premium/revoke", json={}, headers=headers
    )
    assert revoked.json()["plan"] == "free"
    again = await client.post(f"/api/v1/admin/users/{uid}/premium/revoke", json={}, headers=headers)
    assert again.status_code == 400

    off = await client.post(
        f"/api/v1/admin/users/{uid}/active", json={"active": False}, headers=headers
    )
    assert off.json()["is_active"] is False
    assert (await client.get("/api/v1/me", headers=player)).status_code == 401
    self_off = await client.post(
        f"/api/v1/admin/users/{boss_id}/active", json={"active": False}, headers=headers
    )
    assert self_off.status_code == 400


async def test_admin_changes_phone_and_resets_password(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_factory() as session:
        found = await admin.search_users(session, "97111111")
        assert [u.phone for u in found] == ["+22997111111"]
        user = await admin.change_phone(session, "+229 97 11 11 11", "+229 61 00 00 00")
        assert user.phone == "+22961000000"
        _, password = await admin.reset_password(session, "+22961000000")
        await session.commit()
    old = await client.post(
        "/api/v1/auth/login", json={"phone": "+22961000000", "password": "12345678"}
    )
    assert old.status_code == 401
    new = await client.post(
        "/api/v1/auth/login", json={"phone": "+22961000000", "password": password}
    )
    assert new.status_code == 200

    other = await client.post(
        "/api/v1/auth/register",
        json={"phone": "+22997222222", "password": "motdepasse", "display_name": "Ama",
              "country": "BJ", "adult": True},
    )  # fmt: skip
    assert other.status_code == 201
    async with db_factory() as session:
        with pytest.raises(AppError, match="déjà utilisé"):
            await admin.change_phone(session, "+22997222222", "+22961000000")
