"""Paiement de Premium par Wave (simulé : aucun appel réseau)."""

import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from footprono.main import create_app
from footprono.payments import wave

from .conftest import make_settings
from .test_accounts import SIGNUP

KEY = "wave_ci_prod_cle-test"


class FakeWave:
    """Wave : chaque référence a l'état choisi par le test."""

    def __init__(self) -> None:
        self.inits: list[dict[str, Any]] = []
        self.states: dict[str, dict[str, Any]] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {KEY}"
        if request.method == "POST" and request.url.path == "/v1/checkout/sessions":
            body = json.loads(request.content)
            self.inits.append(body)
            return httpx.Response(200, json={
                "id": "cos-1", "wave_launch_url": f"https://pay.wave.com/c/{body['client_reference']}",
                "checkout_status": "open", "payment_status": "processing", **body,
            })  # fmt: skip
        assert request.url.path == "/v1/checkout/sessions/search"
        reference = request.url.params["client_reference"]
        if reference not in self.states:
            return httpx.Response(200, json={"result": []})
        return httpx.Response(200, json={"result": [{
            "id": "cos-1", "client_reference": reference, "amount": "2000", "currency": "XOF",
            "checkout_status": "open", "payment_status": "processing", **self.states[reference],
        }]})  # fmt: skip

    def open(self, reference: str) -> None:
        self.states[reference] = {}

    def pay(self, reference: str, **extra: Any) -> None:
        self.states[reference] = {
            "checkout_status": "complete", "payment_status": "succeeded",
            "transaction_id": "T_1", **extra,
        }  # fmt: skip


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeWave:
    fake = FakeWave()
    monkeypatch.setattr(wave, "test_transport", httpx.MockTransport(fake.handler))
    return fake


async def _app(**overrides: Any) -> Any:
    application: FastAPI = create_app(
        make_settings(public_url="https://footproba.duckdns.org", **overrides)
    )
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
async def http(db_engine: object) -> Any:
    async for client in _app(wave_api_key=KEY, paystack_secret_key="sk_test_x"):
        yield client


async def _buy(http: AsyncClient, body: dict[str, Any] | None) -> tuple[dict[str, str], Any]:
    r = await http.post("/api/v1/auth/register", json={**SIGNUP, "phone": "+2250700000555"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    created = await http.post("/api/v1/payments/premium", headers=headers, json=body)
    return headers, created


async def test_methods_listed_wave_first(http: AsyncClient) -> None:
    methods = (await http.get("/api/v1/payments/methods")).json()
    assert (methods["price"], methods["currency"], methods["days"]) == (2000, "XOF", 30)
    assert [m["id"] for m in methods["methods"]] == ["wave", "paystack"]
    assert methods["manual"] is None


async def test_wave_payment_verified_then_premium(http: AsyncClient, fake: FakeWave) -> None:
    headers, created = await _buy(http, {"method": "wave"})
    assert created.status_code == 201, created.text
    payment = created.json()
    reference = payment["transaction_id"]
    assert payment["payment_url"] == f"https://pay.wave.com/c/{reference}"
    sent = fake.inits[0]
    assert (sent["amount"], sent["currency"]) == ("2000", "XOF")
    back = f"https://footproba.duckdns.org/api/v1/payments/wave/return?transaction_id={reference}"
    assert sent["success_url"] == sent["error_url"] == back

    fake.open(reference)
    pending = (await http.get(f"/api/v1/payments/{payment['id']}", headers=headers)).json()
    assert pending["status"] == "pending"
    assert (await http.get("/api/v1/me", headers=headers)).json()["plan"]["name"] == "free"
    fake.pay(reference)
    page = await http.get("/api/v1/payments/wave/return", params={"transaction_id": reference})
    assert "Paiement reçu" in page.text
    done = (await http.get(f"/api/v1/payments/{payment['id']}", headers=headers)).json()
    assert (done["status"], done["method"]) == ("accepted", "wave")
    me = (await http.get("/api/v1/me", headers=headers)).json()
    assert me["plan"]["name"] == "premium"


async def test_wave_wrong_amount_never_grants(http: AsyncClient, fake: FakeWave) -> None:
    headers, created = await _buy(http, {"method": "wave"})
    payment = created.json()
    fake.pay(payment["transaction_id"], amount="1000")
    done = (await http.get(f"/api/v1/payments/{payment['id']}", headers=headers)).json()
    assert done["status"] == "error"
    assert (await http.get("/api/v1/me", headers=headers)).json()["plan"]["name"] == "free"


async def test_wave_cancelled_is_refused(http: AsyncClient, fake: FakeWave) -> None:
    headers, created = await _buy(http, {"method": "wave"})
    payment = created.json()
    fake.states[payment["transaction_id"]] = {"payment_status": "cancelled"}
    done = (await http.get(f"/api/v1/payments/{payment['id']}", headers=headers)).json()
    assert done["status"] == "refused"


async def test_wave_webhook_is_only_a_signal(http: AsyncClient, fake: FakeWave) -> None:
    headers, created = await _buy(http, {"method": "wave"})
    reference = created.json()["transaction_id"]
    # Un message forgé qui se dit « réussi » : Wave dit « en cours », rien n'est accordé.
    event = {"type": "checkout.session.completed",
             "data": {"client_reference": reference, "payment_status": "succeeded"}}  # fmt: skip
    fake.open(reference)
    notify = "/api/v1/payments/wave/notify"
    assert (await http.post(notify, json=event)).json() == {"status": "pending"}
    assert (await http.post(notify, content=b"pas du json")).json() == {"status": "ignored"}
    fake.pay(reference)
    assert (await http.post(notify, json=event)).json() == {"status": "accepted"}
    assert (await http.get("/api/v1/me", headers=headers)).json()["plan"]["name"] == "premium"


async def test_unknown_method_falls_back_to_first(http: AsyncClient, fake: FakeWave) -> None:
    _, created = await _buy(http, {"method": "inconnu"})
    assert created.status_code == 201, created.text
    assert created.json()["payment_url"].startswith("https://pay.wave.com/")
    assert len(fake.inits) == 1


async def test_manual_wave_number_shown(db_engine: object) -> None:
    async for client in _app(wave_manual_number="+2250700000000"):
        methods = (await client.get("/api/v1/payments/methods")).json()
        assert methods["methods"] == []
        assert methods["manual"] == {
            "wave_number": "+2250700000000", "whatsapp": "+2250500649904",
        }  # fmt: skip
