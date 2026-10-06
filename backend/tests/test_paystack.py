"""Paiement de Premium par Paystack (simulé : aucun appel réseau)."""

import hashlib
import hmac
import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from footprono.main import create_app
from footprono.payments import paystack

from .conftest import make_settings
from .test_accounts import SIGNUP

SECRET = "sk_test_cle-paystack"


class FakePaystack:
    """Paystack : chaque référence a l'état choisi par le test."""

    def __init__(self) -> None:
        self.inits: list[dict[str, Any]] = []
        self.states: dict[str, dict[str, Any]] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        if request.url.path == "/transaction/initialize":
            body = json.loads(request.content)
            self.inits.append(body)
            return httpx.Response(200, json={"status": True, "message": "ok", "data": {
                "authorization_url": f"https://checkout.paystack.com/{body['reference']}",
                "access_code": "code", "reference": body["reference"],
            }})  # fmt: skip
        reference = request.url.path.rsplit("/", 1)[-1]
        state = self.states.get(reference, {"status": "ongoing"})
        return httpx.Response(200, json={"status": True, "message": "ok", "data": {
            "reference": reference, "currency": "XOF", "amount": 200000,
            "channel": "mobile_money", "customer": {"email": "x@y.z", "phone": "+225…"},
            **state,
        }})  # fmt: skip

    def pay(self, reference: str, **extra: Any) -> None:
        self.states[reference] = {"status": "success", "paid_at": "2026-10-06T10:00:00Z", **extra}


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakePaystack:
    fake = FakePaystack()
    monkeypatch.setattr(paystack, "test_transport", httpx.MockTransport(fake.handler))
    return fake


@pytest.fixture
async def http(db_engine: object) -> Any:
    application: FastAPI = create_app(
        make_settings(paystack_secret_key=SECRET, public_url="https://footproba.duckdns.org")
    )
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def _buy(http: AsyncClient) -> tuple[dict[str, str], dict[str, Any]]:
    r = await http.post("/api/v1/auth/register", json={**SIGNUP, "phone": "+2250700000444"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    created = await http.post("/api/v1/payments/premium", headers=headers)
    assert created.status_code == 201, created.text
    return headers, created.json()


def _signed(body: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    raw = json.dumps(body).encode()
    signature = hmac.new(SECRET.encode(), raw, hashlib.sha512).hexdigest()
    return raw, {"x-paystack-signature": signature, "content-type": "application/json"}


async def test_paystack_payment_verified_then_premium(
    http: AsyncClient, fake: FakePaystack
) -> None:
    headers, payment = await _buy(http)
    reference = payment["transaction_id"]
    assert payment["payment_url"] == f"https://checkout.paystack.com/{reference}"
    sent = fake.inits[0]
    assert (sent["amount"], sent["currency"]) == (200000, "XOF")  # francs CFA multipliés par 100
    assert sent["channels"] == ["mobile_money", "card"]
    assert sent["email"].startswith("joueur")
    assert sent["email"].endswith("@footproba.duckdns.org")
    assert sent["callback_url"] == "https://footproba.duckdns.org/api/v1/payments/paystack/return"

    assert (await http.get("/api/v1/me", headers=headers)).json()["plan"]["name"] == "free"
    pending = (await http.get(f"/api/v1/payments/{payment['id']}", headers=headers)).json()
    assert pending["status"] == "pending"
    fake.pay(reference)
    page = await http.get("/api/v1/payments/paystack/return", params={"reference": reference})
    assert "Paiement reçu" in page.text
    done = (await http.get(f"/api/v1/payments/{payment['id']}", headers=headers)).json()
    assert (done["status"], done["method"]) == ("accepted", "mobile_money")
    me = (await http.get("/api/v1/me", headers=headers)).json()
    assert me["plan"]["name"] == "premium"
    assert me["plan"]["days_left"] in (29, 30)


async def test_paystack_wrong_amount_never_grants(http: AsyncClient, fake: FakePaystack) -> None:
    headers, payment = await _buy(http)
    trial = (await http.get("/api/v1/me", headers=headers)).json()["plan"]["days_left"]
    fake.pay(payment["transaction_id"], amount=100000)  # 1 000 F au lieu de 2 000 F
    done = (await http.get(f"/api/v1/payments/{payment['id']}", headers=headers)).json()
    assert done["status"] == "error"
    assert (await http.get("/api/v1/me", headers=headers)).json()["plan"]["days_left"] == trial


async def test_paystack_webhook_is_checked(http: AsyncClient, fake: FakePaystack) -> None:
    headers, payment = await _buy(http)
    reference = payment["transaction_id"]
    event = {"event": "charge.success", "data": {"reference": reference}}
    raw, good = _signed(event)
    forged = await http.post(
        "/api/v1/payments/paystack/notify", content=raw,
        headers={**good, "x-paystack-signature": "0" * 128},
    )  # fmt: skip
    assert forged.json() == {"status": "ignored"}
    # Signature juste mais paiement pas encore confirmé par Paystack : rien n'est accordé.
    assert (
        await http.post("/api/v1/payments/paystack/notify", content=raw, headers=good)
    ).json() == {"status": "pending"}
    fake.pay(reference)
    assert (
        await http.post("/api/v1/payments/paystack/notify", content=raw, headers=good)
    ).json() == {"status": "accepted"}
    me = (await http.get("/api/v1/me", headers=headers)).json()
    assert me["plan"]["days_left"] in (29, 30)
