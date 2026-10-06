"""Connexion avec Google : jeton Firebase vérifié par le serveur (clé d'essai, aucun réseau)."""

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from httpx import AsyncClient

from footprono.accounts import google

PROJECT = "footprono-56616"
API = "/api/v1"


def _key_and_cert() -> tuple[rsa.RSAPrivateKey, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "essai")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return key, cert.public_bytes(serialization.Encoding.PEM).decode()


KEY, CERT = _key_and_cert()
OTHER_KEY, _ = _key_and_cert()


@pytest.fixture(autouse=True)
def certificates(monkeypatch: pytest.MonkeyPatch) -> None:
    async def source() -> dict[str, str]:
        return {"cle-1": CERT}

    monkeypatch.setattr(google, "certificate_source", source)


def token(
    google_id: str = "g-111",
    email: str = "kossi@gmail.com",
    *,
    key: rsa.RSAPrivateKey = KEY,
    provider: str = "google.com",
    **claims: Any,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": f"https://securetoken.google.com/{PROJECT}",
        "aud": PROJECT,
        "sub": "firebase-" + google_id,
        "iat": now,
        "exp": now + 3600,
        "email": email,
        "email_verified": True,
        "name": "Kossi Mensah",
        "firebase": {"sign_in_provider": provider, "identities": {"google.com": [google_id]}},
        **claims,
    }
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "cle-1"})


def _auth(access: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access}"}


async def test_first_google_login_creates_the_account(
    client: AsyncClient, db_engine: object
) -> None:
    unknown = await client.post(f"{API}/auth/google", json={"id_token": token()})
    assert unknown.status_code == 404
    error = unknown.json()["error"]
    assert error["code"] == "google_account_unknown"
    assert error["details"] == {"email": "kossi@gmail.com", "name": "Kossi Mensah"}

    minor = await client.post(
        f"{API}/auth/google/register", json={"id_token": token(), "country": "CI", "adult": False}
    )
    assert minor.status_code == 400
    created = await client.post(
        f"{API}/auth/google/register", json={"id_token": token(), "country": "ci", "adult": True}
    )
    assert created.status_code == 201, created.text
    me = (await client.get(f"{API}/me", headers=_auth(created.json()["access_token"]))).json()
    assert (me["phone"], me["email"], me["display_name"], me["country"]) == (
        None, "kossi@gmail.com", "Kossi Mensah", "CI",
    )  # fmt: skip
    assert (me["google_linked"], me["has_password"]) == (True, False)
    assert me["plan"]["name"] == "free"  # pas d'essai, comme par numéro
    assert me["wallet"]["balance"] > 0

    again = await client.post(
        f"{API}/auth/google/register", json={"id_token": token(), "country": "CI", "adult": True}
    )
    assert again.status_code == 409
    login = await client.post(f"{API}/auth/google", json={"id_token": token()})
    assert login.status_code == 200
    assert (await client.get(f"{API}/me", headers=_auth(login.json()["access_token"]))).json()[
        "id"
    ] == me["id"]

    # Pas de mot de passe à changer ni de Google à délier : ce serait perdre le compte.
    access = _auth(login.json()["access_token"])
    password = await client.post(
        f"{API}/me/password", json={"current_password": "", "new_password": "nouveau-123"},
        headers=access,
    )  # fmt: skip
    assert password.status_code == 400
    assert (await client.delete(f"{API}/me/google", headers=access)).status_code == 400


@pytest.mark.parametrize(
    "bad",
    [
        token(key=OTHER_KEY),  # signature d'une autre clé
        token(aud="autre-projet"),
        token(iss="https://securetoken.google.com/autre-projet"),
        token(exp=int(time.time()) - 3600),  # expiré
        token(provider="password"),  # connexion Firebase qui n'est pas Google
        token(email_verified=False),
        "pas-un-jeton",
    ],
)
async def test_invalid_google_tokens_are_refused(
    client: AsyncClient, db_engine: object, bad: str
) -> None:
    r = await client.post(f"{API}/auth/google", json={"id_token": bad})
    assert r.status_code == 401
    assert "connexion" in r.json()["error"]["message"] or "Google" in r.json()["error"]["message"]


async def test_phone_account_links_and_unlinks_google(
    client: AsyncClient, db_engine: object
) -> None:
    signup = {
        "phone": "+225 05 00 00 00 01", "password": "motdepasse-1", "display_name": "Afi",
        "country": "CI", "adult": True,
    }  # fmt: skip
    access = _auth((await client.post(f"{API}/auth/register", json=signup)).json()["access_token"])
    other = _auth(
        (
            await client.post(
                f"{API}/auth/register", json={**signup, "phone": "+225 05 00 00 00 02"}
            )
        ).json()["access_token"]
    )

    linked = await client.post(
        f"{API}/me/google", json={"id_token": token("g-afi", "afi@gmail.com")}, headers=access
    )
    assert linked.status_code == 200, linked.text
    assert (linked.json()["google_linked"], linked.json()["email"]) == (True, "afi@gmail.com")
    # Même compte FootProba, Premium et solde compris, avec Google ou le numéro.
    by_google = await client.post(
        f"{API}/auth/google", json={"id_token": token("g-afi", "afi@gmail.com")}
    )
    me = (await client.get(f"{API}/me", headers=_auth(by_google.json()["access_token"]))).json()
    assert me["phone"] == "+2250500000001"

    taken = await client.post(
        f"{API}/me/google", json={"id_token": token("g-afi", "afi@gmail.com")}, headers=other
    )
    assert taken.status_code == 409

    unlinked = await client.delete(f"{API}/me/google", headers=access)
    assert unlinked.json()["google_linked"] is False
    after = await client.post(
        f"{API}/auth/google", json={"id_token": token("g-afi", "afi@gmail.com")}
    )
    assert after.status_code == 404


async def test_google_account_deletion_asks_google_again(
    client: AsyncClient, db_engine: object
) -> None:
    created = await client.post(
        f"{API}/auth/google/register",
        json={"id_token": token("g-del"), "country": "CI", "adult": True},
    )
    access = _auth(created.json()["access_token"])
    wrong = await client.post(
        f"{API}/me/delete", json={"google_id_token": token("g-autre")}, headers=access
    )
    assert wrong.status_code == 401
    done = await client.post(
        f"{API}/me/delete", json={"google_id_token": token("g-del")}, headers=access
    )
    assert done.status_code == 204
    assert (
        await client.post(f"{API}/auth/google", json={"id_token": token("g-del")})
    ).status_code == 404


async def test_support_whatsapp_link(client: AsyncClient) -> None:
    support = (await client.get(f"{API}/app/support")).json()
    assert support == {
        "whatsapp": "+2250500649904",
        "whatsapp_url": "https://wa.me/2250500649904",
    }


async def test_console_manages_a_google_account_without_phone(
    client: AsyncClient, db_factory: Any
) -> None:
    from footprono.accounts import admin
    from footprono.accounts import service as accounts

    from .conftest import make_settings

    async with db_factory() as session:
        await accounts.register(
            session, make_settings(), phone="+22505000000099", password="admin-123",
            display_name="Admin", country="CI", adult=True,
        )  # fmt: skip
        await admin.set_role(session, "+22505000000099", "admin")
        await session.commit()
    boss = _auth(
        (
            await client.post(
                f"{API}/auth/console-login",
                json={"phone": "+22505000000099", "password": "admin-123"},
            )
        ).json()["access_token"]
    )
    await client.post(
        f"{API}/auth/google/register",
        json={"id_token": token("g-c"), "country": "CI", "adult": True},
    )
    users = (await client.get(f"{API}/admin/users", params={"q": "kossi@"}, headers=boss)).json()
    assert [(u["phone"], u["email"]) for u in users] == [(None, "kossi@gmail.com")]
    uid = users[0]["id"]
    role = await client.post(f"{API}/admin/users/{uid}/role", json={"role": "admin"}, headers=boss)
    assert role.json()["role"] == "admin"
    phone = await client.post(
        f"{API}/admin/users/{uid}/phone", json={"phone": "+225 07 00 00 00 01"}, headers=boss
    )
    assert phone.json()["phone"] == "+2250700000001"
