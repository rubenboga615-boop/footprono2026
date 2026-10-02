"""Suppression du compte : données personnelles effacées, paiements gardés sans la personne."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.accounts.models import User, Wallet
from footprono.bookmaker.models import Bet
from footprono.payments.models import Payment

from .test_bets import _login, _sel, world  # noqa: F401 (fixture partagée)

Factory = async_sessionmaker[AsyncSession]


async def _count(factory: Factory, model: Any, **where: Any) -> int:
    async with factory() as session:
        stmt = select(func.count()).select_from(model)
        for k, v in where.items():
            stmt = stmt.where(getattr(model, k) == v)
        return int(await session.scalar(stmt) or 0)


async def test_delete_from_app(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    headers = await _login(client)
    uid = world["user_id"]
    bet = await client.post(
        "/api/v1/bets",
        json={"stake": 1000, "selections": [_sel(world["m1"], "1X2", "home")]},
        headers=headers,
    )
    assert bet.status_code == 201, bet.text
    async with db_factory() as session:
        for status in ("accepted", "pending"):
            session.add(
                Payment(
                    user_id=uid, provider="cinetpay", transaction_id=f"T-{status}", amount=2000,
                    currency="XOF", days=30, status=status, raw={"customer_phone": "+22997111111"},
                )
            )  # fmt: skip
        await session.commit()

    wrong = await client.post("/api/v1/me/delete", json={"password": "mauvais"}, headers=headers)
    assert wrong.status_code == 401
    assert await _count(db_factory, User, id=uid) == 1

    ok = await client.post("/api/v1/me/delete", json={"password": "12345678"}, headers=headers)
    assert ok.status_code == 204
    assert await _count(db_factory, User, id=uid) == 0
    assert await _count(db_factory, Wallet, user_id=uid) == 0
    assert await _count(db_factory, Bet, user_id=uid) == 0
    async with db_factory() as session:
        payments = (await session.scalars(select(Payment).order_by(Payment.transaction_id))).all()
        assert [(p.user_id, p.status, p.raw, p.amount) for p in payments] == [
            (None, "accepted", {}, 2000),
            (None, "cancelled", {}, 2000),
        ]
    # Le jeton ne sert plus à rien ; le numéro est libre.
    assert (await client.get("/api/v1/me", headers=headers)).status_code == 401
    again = await client.post(
        "/api/v1/auth/login", json={"phone": "+22997111111", "password": "12345678"}
    )
    assert again.status_code == 401


async def test_delete_without_app(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    page = await client.get("/suppression-compte")
    assert page.status_code == 200
    assert "Supprimer mon compte FootProno" in page.text
    bad = await client.post(
        "/api/v1/account/delete", json={"phone": "+22997111111", "password": "x"}
    )
    assert bad.status_code == 401
    ok = await client.post(
        "/api/v1/account/delete", json={"phone": "+229 97 11 11 11", "password": "12345678"}
    )
    assert ok.status_code == 204
    assert await _count(db_factory, User, id=world["user_id"]) == 0
