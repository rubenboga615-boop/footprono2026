"""Sécurité de la console : code à 6 chiffres, sessions annulables, journal des actions,
jetons de l'application révoqués après un changement de mot de passe."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.accounts import admin, totp
from footprono.accounts import service as accounts

from .conftest import TEST_REDIS_URL, make_settings

Factory = async_sessionmaker[AsyncSession]
PHONE = "+2250500000077"
LOGIN = {"phone": PHONE, "password": "admin-secret-1"}


@pytest.fixture(autouse=True)
async def clean_console_keys() -> None:
    """Sessions et codes d'un test précédent (mêmes numéros de compte) effacés."""
    redis = Redis.from_url(TEST_REDIS_URL)
    try:
        keys = [k async for k in redis.scan_iter("console:*")]
        if keys:
            await redis.delete(*keys)
    finally:
        await redis.aclose()


def test_totp_matches_the_rfc_6238_reference() -> None:
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # « 12345678901234567890 »
    assert totp.code_at(secret, 59 // 30) == "287082"  # 94287082 sur 6 chiffres
    assert totp.matching_counter(secret, "287 082", now=59) == 1
    assert totp.matching_counter(secret, "287082", now=59 + 90) is None  # trop ancien
    settings = make_settings()
    assert totp.unseal(settings, totp.seal(settings, secret)) == secret


async def _admin(db_factory: Factory) -> None:
    async with db_factory() as session:
        await accounts.register(
            session, make_settings(), phone=PHONE, password=LOGIN["password"],
            display_name="Patron", country="CI", adult=True,
        )  # fmt: skip
        await admin.set_role(session, PHONE, "admin")
        await session.commit()


def _auth(r: object) -> dict[str, str]:
    return {"Authorization": f"Bearer {r.json()['access_token']}"}  # type: ignore[attr-defined]


async def test_security_code_then_sessions_and_audit(
    client: AsyncClient, db_factory: Factory
) -> None:
    await _admin(db_factory)
    first = _auth(await client.post("/api/v1/auth/console-login", json=LOGIN))
    status = (await client.get("/api/v1/admin/security", headers=first)).json()
    assert status == {"totp_enabled": False, "sessions": 1, "session_hours": 12}

    setup = (await client.post("/api/v1/admin/security/totp/setup", headers=first)).json()
    secret = setup["secret"]
    assert setup["uri"].startswith("otpauth://totp/FootProba%20Console")
    wrong = await client.post(
        "/api/v1/admin/security/totp/enable", json={"code": "000000"}, headers=first
    )
    assert wrong.status_code == 400
    code = totp.code_at(secret, totp.current_counter())
    if code == "000000":  # une chance sur un million
        code = totp.code_at(secret, totp.current_counter() - 1)
    enabled = await client.post(
        "/api/v1/admin/security/totp/enable", json={"code": code}, headers=first
    )
    assert enabled.json() == {"totp_enabled": True}

    # Connexion : le code n'est demandé qu'après un mot de passe juste.
    bad_password = await client.post(
        "/api/v1/auth/console-login", json={**LOGIN, "password": "faux"}
    )
    assert bad_password.json()["error"]["code"] == "unauthorized"
    no_code = await client.post("/api/v1/auth/console-login", json=LOGIN)
    assert (no_code.status_code, no_code.json()["error"]["code"]) == (401, "totp_required")
    wrong_code = await client.post("/api/v1/auth/console-login", json={**LOGIN, "code": "12345"})
    assert wrong_code.status_code == 401
    fresh = totp.code_at(secret, totp.current_counter())
    second = await client.post("/api/v1/auth/console-login", json={**LOGIN, "code": fresh})
    assert second.status_code == 200
    replay = await client.post("/api/v1/auth/console-login", json={**LOGIN, "code": fresh})
    assert replay.status_code == 401  # un code déjà utilisé ne sert pas deux fois
    second_headers = _auth(second)

    # Déconnexion de cette session, puis de toutes les autres.
    assert (
        await client.post("/api/v1/admin/console/logout", headers=second_headers)
    ).status_code == 204
    assert (await client.get("/api/v1/admin/console/me", headers=second_headers)).status_code == 401
    me = (await client.get("/api/v1/admin/console/me", headers=first)).json()
    assert me["totp_enabled"] is True
    closed = (await client.post("/api/v1/admin/console/logout-all", headers=first)).json()
    assert closed == {"closed": 1}
    assert (await client.get("/api/v1/admin/console/me", headers=first)).status_code == 401

    third = _auth(
        await client.post(
            "/api/v1/auth/console-login",
            json={**LOGIN, "code": totp.code_at(secret, totp.current_counter() + 1)},
        )
    )
    journal = (await client.get("/api/v1/admin/console/audit", headers=third)).json()
    actions = [row["action"] for row in journal]
    assert actions[:2] == ["console_login", "console_logout_all"]
    assert "totp_enabled" in actions
    assert "console_code_refused" in actions
    assert journal[0]["admin"] == "Patron"


async def test_admin_changes_are_written_in_the_journal(
    client: AsyncClient, db_factory: Factory
) -> None:
    await _admin(db_factory)
    async with db_factory() as session:
        player = await accounts.register(
            session, make_settings(), phone="+2250700000088", password="joueur-123",
            display_name="Awa", country="CI", adult=True,
        )  # fmt: skip
        await session.commit()
        player_id = player.id
    headers = _auth(await client.post("/api/v1/auth/console-login", json=LOGIN))
    await client.post(
        f"/api/v1/admin/users/{player_id}/premium", json={"days": 30}, headers=headers
    )
    await client.post(f"/api/v1/admin/users/{player_id}/password-reset", headers=headers)
    journal = (await client.get("/api/v1/admin/console/audit", headers=headers)).json()
    assert [(r["action"], r["target_user_id"]) for r in journal[:2]] == [
        ("password_reset", player_id),
        ("premium_grant", player_id),
    ]
    assert "Awa (+2250700000088)" in journal[1]["summary"]


async def test_password_change_signs_out_the_other_phones(
    client: AsyncClient, db_factory: Factory
) -> None:
    async with db_factory() as session:
        user = await accounts.register(
            session, make_settings(), phone="+2250700000099", password="ancien-123",
            display_name="Yao", country="CI", adult=True,
        )  # fmt: skip
        await session.commit()
        user_id = user.id
    settings = make_settings()
    # Jeton d'un autre téléphone, émis il y a une heure.
    issued = datetime.now(UTC) - timedelta(hours=1)
    old_phone = jwt.encode(
        {"sub": str(user_id), "iat": issued, "exp": issued + timedelta(days=30)},
        settings.secret_key.get_secret_value(),  # type: ignore[union-attr]
        algorithm="HS256",
    )
    other = {"Authorization": f"Bearer {old_phone}"}
    assert (await client.get("/api/v1/me", headers=other)).status_code == 200
    changed = await client.post(
        "/api/v1/me/password",
        json={"current_password": "ancien-123", "new_password": "nouveau-123"},
        headers=other,
    )
    assert changed.status_code == 200
    assert (await client.get("/api/v1/me", headers=other)).status_code == 401
    assert (await client.get("/api/v1/me", headers=_auth(changed))).status_code == 200
