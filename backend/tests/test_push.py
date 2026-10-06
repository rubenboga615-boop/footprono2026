"""Notifications push (Firebase Cloud Messaging) : appareils, envoi, jetons périmés.

Firebase est simulé (httpx.MockTransport) : aucun appel réseau.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.accounts.cli import main as admin_cli
from footprono.bookmaker.settlement import settle_bets
from footprono.football.models import Match, MatchStatus
from footprono.main import create_app
from footprono.notifications import push
from footprono.notifications.models import PushDevice

from .conftest import make_settings
from .test_accounts import SIGNUP
from .test_bets import _login, _sel, world  # noqa: F401 (fixture partagée)

Factory = async_sessionmaker[AsyncSession]
TOKEN_A = "jeton-appareil-a-" + "x" * 40
TOKEN_B = "jeton-appareil-b-" + "y" * 40


@pytest.fixture(scope="module")
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def account_file(tmp_path: Path, private_key: rsa.RSAPrivateKey) -> Path:
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    path = tmp_path / "firebase.json"
    path.write_text(
        json.dumps(
            {
                "type": "service_account",
                "project_id": "footprono-test",
                "client_email": "fcm@footprono-test.iam.gserviceaccount.com",
                "private_key": pem,
                "token_uri": "https://oauth2.example/token",
            }
        )
    )
    return path


class FakeFirebase:
    """Serveur OAuth2 + FCM simulé ; TOKEN_B est un appareil désinscrit."""

    def __init__(self, private_key: rsa.RSAPrivateKey) -> None:
        self.public_key = private_key.public_key()
        self.messages: list[dict[str, Any]] = []
        self.token_requests = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.example":
            self.token_requests += 1
            form = dict(httpx.QueryParams(request.content.decode()))
            claims = jwt.decode(
                form["assertion"], self.public_key, algorithms=["RS256"],
                audience="https://oauth2.example/token",
            )  # fmt: skip
            assert claims["scope"] == push.SCOPE
            return httpx.Response(200, json={"access_token": "acces-google", "expires_in": 3600})
        assert request.url.path == "/v1/projects/footprono-test/messages:send"
        assert request.headers["Authorization"] == "Bearer acces-google"
        message = json.loads(request.content)["message"]
        if message["token"] == TOKEN_B:
            return httpx.Response(
                404,
                json={
                    "error": {
                        "code": 404,
                        "status": "NOT_FOUND",
                        "details": [{"errorCode": "UNREGISTERED"}],
                    }
                },
            )
        self.messages.append(message)
        return httpx.Response(200, json={"name": "projects/footprono-test/messages/1"})


def _sender(account_file: Path, fake: FakeFirebase) -> push.FcmSender:
    return push.FcmSender(
        push.ServiceAccount.load(account_file),
        httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)),
    )


def test_service_account_errors_are_explicit(tmp_path: Path) -> None:
    bad = tmp_path / "google-services.json"
    bad.write_text(json.dumps({"project_info": {"project_id": "x"}}))
    with pytest.raises(push.PushConfigError, match="compte de service"):
        push.ServiceAccount.load(bad)
    with pytest.raises(push.PushConfigError, match="illisible"):
        push.ServiceAccount.load(tmp_path / "absent.json")
    assert push.status(make_settings())["enabled"] is False
    assert push.status(make_settings(fcm_credentials_file=bad))["enabled"] is False


def test_status_with_a_valid_key(account_file: Path) -> None:
    assert push.status(make_settings(fcm_credentials_file=account_file)) == {
        "enabled": True,
        "project_id": "footprono-test",
    }
    assert push.FcmSender.from_settings(make_settings()) is None
    assert push.FcmSender.from_settings(make_settings(fcm_credentials_file="")) is None
    sender = push.FcmSender.from_settings(
        make_settings(fcm_credentials_file=account_file, public_url="https://fp.example/")
    )
    assert sender is not None
    assert sender.web_link == "https://fp.example/app/"


async def test_web_push_link_and_key(
    account_file: Path, private_key: rsa.RSAPrivateKey, db_engine: object
) -> None:
    fake = FakeFirebase(private_key)
    sender = push.FcmSender(
        push.ServiceAccount.load(account_file),
        httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)),
        web_link="https://fp.example/app/",
    )
    assert (await sender.send_one(TOKEN_A, "Titre", "Texte", {"kind": "test"})).status_code == 200
    assert fake.messages[0]["webpush"]["fcm_options"]["link"] == "https://fp.example/app/"
    await sender.aclose()

    for overrides, expected in (
        ({"web_push_vapid_key": "BCle"}, None),  # sans clé Firebase : rien ne partirait
        ({"web_push_vapid_key": "BCle", "fcm_credentials_file": account_file}, "BCle"),
    ):
        application = create_app(make_settings(**overrides))
        async with application.router.lifespan_context(application):
            transport = ASGITransport(app=application, raise_app_exceptions=False)
            async with AsyncClient(transport=transport, base_url="http://test") as http:
                r = await http.get("/api/v1/app/web-push")
                assert r.json() == {"vapid_key": expected}


async def test_devices_register_move_and_remove(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    kofi = await _login(client)
    assert (
        await client.post("/api/v1/me/devices", json={"token": TOKEN_A}, headers=kofi)
    ).status_code == 204
    # Même téléphone, même jeton : pas de doublon.
    await client.post("/api/v1/me/devices", json={"token": TOKEN_A}, headers=kofi)
    signup = await client.post("/api/v1/auth/register", json=SIGNUP)
    other = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    # Un autre compte ouvert sur ce téléphone : l'appareil change de compte.
    await client.post("/api/v1/me/devices", json={"token": TOKEN_A}, headers=other)
    async with db_factory() as session:
        devices = (await session.scalars(select(PushDevice))).all()
        assert len(devices) == 1
        assert devices[0].user_id != world["user_id"]
    # Kofi ne peut pas retirer l'appareil d'un autre compte.
    await client.post("/api/v1/me/devices/remove", json={"token": TOKEN_A}, headers=kofi)
    async with db_factory() as session:
        assert len((await session.scalars(select(PushDevice))).all()) == 1
    await client.post("/api/v1/me/devices/remove", json={"token": TOKEN_A}, headers=other)
    async with db_factory() as session:
        assert (await session.scalars(select(PushDevice))).all() == []
    assert (
        await client.post("/api/v1/me/devices", json={"token": "court"}, headers=kofi)
    ).status_code == 422
    assert (await client.post("/api/v1/me/devices", json={"token": TOKEN_A})).status_code == 401


async def test_settlement_pushes_and_forgets_dead_tokens(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
    account_file: Path,
    private_key: rsa.RSAPrivateKey,
) -> None:
    headers = await _login(client)
    for token in (TOKEN_A, TOKEN_B):
        await client.post("/api/v1/me/devices", json={"token": token}, headers=headers)
    await client.post(
        "/api/v1/bets",
        json={"stake": 2_000, "selections": [_sel(world["m1"], "1X2", "home")]},
        headers=headers,
    )
    async with db_factory() as session:
        await session.execute(
            update(Match)
            .where(Match.id == world["m1"])
            .values(
                status=MatchStatus.FINISHED, home_goals=2, away_goals=0,
                result_source="api_football", api_status="FT",
            )
        )  # fmt: skip
        await session.commit()

    fake = FakeFirebase(private_key)
    sender = _sender(account_file, fake)
    async with db_factory() as session:
        report = await settle_bets(session, push=sender)
    await sender.aclose()

    assert report["notified"] == 1
    assert len(fake.messages) == 1
    message = fake.messages[0]
    assert message["token"] == TOKEN_A
    assert message["notification"]["title"] == "Pari gagné"
    assert message["android"]["notification"]["channel_id"] == push.ANDROID_CHANNEL
    assert message["data"]["kind"] == "bet_settled"
    assert all(isinstance(v, str) for v in message["data"].values())
    async with db_factory() as session:
        tokens = list(await session.scalars(select(PushDevice.token)))
    assert tokens == [TOKEN_A]  # l'appareil désinscrit est oublié


async def test_access_token_is_reused(account_file: Path, private_key: rsa.RSAPrivateKey) -> None:
    fake = FakeFirebase(private_key)
    sender = _sender(account_file, fake)
    for _ in range(3):
        response = await sender.send_one(TOKEN_A, "t", "b", {"n": 1})
        assert response.status_code == 200
    await sender.aclose()
    assert fake.token_requests == 1
    assert fake.messages[0]["data"] == {"n": "1"}


def test_push_test_command_without_key(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.delenv("FP_FCM_CREDENTIALS_FILE", raising=False)
    from footprono.core.config import get_settings

    get_settings.cache_clear()
    assert admin_cli(["push-test", "+22997111111"]) == 1
    assert "FP_FCM_CREDENTIALS_FILE" in capsys.readouterr().err
