"""Comptes et portefeuille fictif."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.accounts import service
from footprono.accounts.models import Wallet
from footprono.accounts.security import hash_password, verify_password
from footprono.core.errors import AppError
from footprono.main import create_app

from .conftest import TEST_REDIS_URL, make_settings

SIGNUP = {
    "phone": "+229 97 00 00 01",
    "password": "motdepasse-solide",
    "display_name": "Kossi",
    "country": "bj",
    "adult": True,
}


def test_password_hashing() -> None:
    stored = hash_password("secret-123")
    assert stored.startswith("scrypt$")
    assert verify_password("secret-123", stored)
    assert not verify_password("secret-124", stored)
    assert hash_password("secret-123") != stored  # sel aléatoire


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("+229 97 00 00 00", "+22997000000"), ("00225-07-12-34-56-78", "+2250712345678")],
)
def test_normalize_phone(raw: str, expected: str) -> None:
    assert service.normalize_phone(raw) == expected


def test_normalize_phone_rejects_local_numbers() -> None:
    with pytest.raises(AppError):
        service.normalize_phone("97000000")


async def test_register_login_me_and_wallet(
    db_factory: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    created = await client.post("/api/v1/auth/register", json=SIGNUP)
    assert created.status_code == 201, created.text
    token = created.json()["access_token"]

    again = await client.post("/api/v1/auth/register", json=SIGNUP)
    assert again.status_code == 409

    minor = await client.post(
        "/api/v1/auth/register", json={**SIGNUP, "phone": "+22997000002", "adult": False}
    )
    assert minor.status_code == 400
    ghana = await client.post(
        "/api/v1/auth/register", json={**SIGNUP, "phone": "+23320000000", "country": "GH"}
    )
    assert ghana.status_code == 400

    bad = await client.post(
        "/api/v1/auth/login", json={"phone": SIGNUP["phone"], "password": "faux-mot-de-passe"}
    )
    assert bad.status_code == 401
    good = await client.post(
        "/api/v1/auth/login", json={"phone": "+22997000001", "password": SIGNUP["password"]}
    )
    assert good.status_code == 200

    assert (await client.get("/api/v1/me")).status_code == 401
    headers = {"Authorization": f"Bearer {token}"}
    me = (await client.get("/api/v1/me", headers=headers)).json()
    assert (me["country"], me["currency"], me["phone"]) == ("BJ", "XOF", "+22997000001")
    assert me["wallet"]["balance"] == 100_000
    assert me["virtual_money"] is True
    entries = (await client.get("/api/v1/me/wallet/entries", headers=headers)).json()
    assert [(e["kind"], e["amount"], e["balance_after"]) for e in entries] == [
        ("opening", 100_000, 100_000)
    ]
    # Solde encore élevé : pas de rechargement.
    refused = await client.post("/api/v1/me/wallet/refill", headers=headers)
    assert refused.status_code == 400
    forged = await client.get("/api/v1/me", headers={"Authorization": "Bearer faux"})
    assert forged.status_code == 401


async def test_wallet_moves_and_refill(db_factory: async_sessionmaker[AsyncSession]) -> None:
    settings = make_settings()
    async with db_factory() as session:
        user = await service.register(
            session, settings, phone="+22170000000", password="12345678", display_name="Awa",
            country="SN", adult=True,
        )  # fmt: skip
        await session.commit()
        user_id = user.id

    async with db_factory() as session:
        entry = await service.move(session, user_id, -99_500, "stake", bet_id=1)
        assert entry.balance_after == 500
        with pytest.raises(service.InsufficientFundsError):
            await service.move(session, user_id, -501, "stake")
        refill = await service.refill(session, settings, user_id)
        assert (refill.amount, refill.balance_after) == (99_500, 100_000)
        await session.commit()

    async with db_factory() as session:
        await service.move(session, user_id, -100_000, "stake")
        with pytest.raises(AppError, match="prochain rechargement"):
            await service.refill(session, settings, user_id)
        # Une semaine plus tard, le rechargement redevient possible.
        await session.execute(
            update(Wallet)
            .where(Wallet.user_id == user_id)
            .values(last_refill_at=datetime.now(UTC) - timedelta(days=8))
        )
        again = await service.refill(session, settings, user_id)
        assert again.balance_after == 100_000


async def test_change_password(client: AsyncClient) -> None:
    token = (await client.post("/api/v1/auth/register", json=SIGNUP)).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    url = "/api/v1/me/password"
    wrong = await client.post(
        url, headers=headers, json={"current_password": "x" * 9, "new_password": "nouveau-mdp"}
    )
    assert wrong.status_code == 401
    short = await client.post(
        url, headers=headers, json={"current_password": SIGNUP["password"], "new_password": "court"}
    )
    assert short.status_code == 400
    ok = await client.post(
        url,
        headers=headers,
        json={"current_password": SIGNUP["password"], "new_password": "nouveau-mdp"},
    )
    assert ok.status_code == 200  # nouveau jeton : les autres téléphones sont déconnectés
    assert ok.json()["access_token"]
    phone = SIGNUP["phone"]
    old = await client.post(
        "/api/v1/auth/login", json={"phone": phone, "password": SIGNUP["password"]}
    )
    assert old.status_code == 401
    new = await client.post("/api/v1/auth/login", json={"phone": phone, "password": "nouveau-mdp"})
    assert new.status_code == 200


@pytest.fixture
async def limited_client(db_engine: object) -> AsyncIterator[AsyncClient]:
    """API avec limites de tentatives basses, compteurs remis à zéro."""
    redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    keys = [k async for k in redis.scan_iter("ratelimit:*")]
    if keys:
        await redis.delete(*keys)
    await redis.aclose()
    settings = make_settings(
        login_failures_per_phone=3, login_failures_per_ip=100, registrations_per_ip=2
    )
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http


async def test_login_blocked_after_repeated_failures(limited_client: AsyncClient) -> None:
    created = await limited_client.post("/api/v1/auth/register", json=SIGNUP)
    assert created.status_code == 201
    good = {"phone": SIGNUP["phone"], "password": SIGNUP["password"]}
    # Les connexions réussies ne comptent pas.
    for _ in range(5):
        assert (await limited_client.post("/api/v1/auth/login", json=good)).status_code == 200
    # 3 échecs (numéro écrit de deux façons : même compteur), puis blocage même
    # avec le bon mot de passe.
    for phone in ("+229 97 00 00 01", "+22997000001", "+229 97000001"):
        bad = await limited_client.post(
            "/api/v1/auth/login", json={"phone": phone, "password": "mauvais-mot"}
        )
        assert bad.status_code == 401
    blocked = await limited_client.post("/api/v1/auth/login", json=good)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "too_many_attempts"
    assert blocked.json()["error"]["details"]["retry_after_seconds"] > 0


async def test_registrations_limited_per_address(limited_client: AsyncClient) -> None:
    for n in (2, 3):
        r = await limited_client.post(
            "/api/v1/auth/register", json={**SIGNUP, "phone": f"+2299700000{n}"}
        )
        assert r.status_code == 201
    third = await limited_client.post(
        "/api/v1/auth/register", json={**SIGNUP, "phone": "+22997000004"}
    )
    assert third.status_code == 429
