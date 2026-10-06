"""Paiement de Premium par CinetPay (simulé : aucun appel réseau)."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.accounts.models import SubscriptionEvent, User
from footprono.main import create_app
from footprono.notifications.models import Notification
from footprono.payments import cinetpay
from footprono.payments import service as payment_service
from footprono.payments.models import Payment

from .conftest import make_settings
from .test_accounts import SIGNUP

Factory = async_sessionmaker[AsyncSession]
SITE = "105900001"


class FakeCinetPay:
    """Guichet CinetPay : chaque transaction a l'état choisi par le test."""

    def __init__(self) -> None:
        self.states: dict[str, dict[str, Any]] = {}
        self.inits: list[dict[str, Any]] = []
        self.checks = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert (body["apikey"], body["site_id"]) == ("cle-cinetpay", SITE)
        if request.url.path == "/v2/payment":
            self.inits.append(body)
            return httpx.Response(200, json={
                "code": "201", "message": "CREATED",
                "data": {"payment_token": "t", "payment_url": f"https://checkout.cinetpay.com/payment/{body['transaction_id']}"},
            })  # fmt: skip
        assert request.url.path == "/v2/payment/check"
        self.checks += 1
        state = self.states.get(body["transaction_id"])
        if state is None:
            return httpx.Response(200, json={
                "code": "662", "message": "WAITING_CUSTOMER_PAYMENT",
                "data": {"status": "WAITING_FOR_CUSTOMER", "amount": "2000", "currency": "XOF"},
            })  # fmt: skip
        return httpx.Response(200, json={"code": "00", "message": "SUCCES", "data": state})

    def pay(self, tx: str, amount: str = "2000", status: str = "ACCEPTED") -> None:
        self.states[tx] = {
            "status": status, "amount": amount, "currency": "XOF",
            "payment_method": "OMCIV2", "payment_date": "2026-10-01 12:00:00",
        }  # fmt: skip


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeCinetPay:
    fake = FakeCinetPay()
    monkeypatch.setattr(cinetpay, "test_transport", httpx.MockTransport(fake.handler))
    return fake


def _settings(**overrides: Any) -> Any:
    values: dict[str, Any] = {
        "cinetpay_api_key": "cle-cinetpay",
        "cinetpay_site_id": SITE,
        "public_url": "https://footprono.duckdns.org",
    }
    values.update(overrides)
    return make_settings(**values)


@pytest.fixture
async def pay_app(db_engine: object) -> Any:
    application: FastAPI = create_app(_settings())
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def http(pay_app: FastAPI) -> Any:
    transport = ASGITransport(app=pay_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _signup(http: AsyncClient, phone: str = SIGNUP["phone"]) -> dict[str, str]:  # type: ignore[assignment]
    r = await http.post("/api/v1/auth/register", json={**SIGNUP, "phone": phone})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _user(factory: Factory) -> User:
    async with factory() as session:
        user = await session.scalar(select(User).order_by(User.id.desc()))
        assert user is not None
        return user


async def test_paid_premium_is_verified_and_granted_once(
    http: AsyncClient, fake: FakeCinetPay, db_factory: Factory
) -> None:
    headers = await _signup(http)
    assert (await _user(db_factory)).premium_until is None  # pas d'essai à l'inscription

    created = await http.post("/api/v1/payments/premium", headers=headers)
    assert created.status_code == 201, created.text
    payment = created.json()
    assert (payment["amount"], payment["currency"], payment["days"]) == (2000, "XOF", 30)
    assert payment["payment_url"].startswith("https://checkout.cinetpay.com/")
    sent = fake.inits[0]
    assert (sent["amount"], sent["currency"]) == (2000, "XOF")
    assert sent["notify_url"] == "https://footprono.duckdns.org/api/v1/payments/cinetpay/notify"
    assert sent["return_url"].endswith(
        f"/payments/cinetpay/return?transaction_id={payment['transaction_id']}"
    )

    # Pas encore payé : la notification ne suffit pas, l'état reste « en attente ».
    tx = payment["transaction_id"]
    early = await http.post(
        "/api/v1/payments/cinetpay/notify", data={"cpm_trans_id": tx, "cpm_site_id": SITE}
    )
    assert early.json() == {"status": "pending"}
    assert (await http.get(f"/api/v1/payments/{payment['id']}", headers=headers)).json()[
        "status"
    ] == "pending"

    fake.pay(tx)
    paid = await http.post(
        "/api/v1/payments/cinetpay/notify", data={"cpm_trans_id": tx, "cpm_site_id": SITE}
    )
    assert paid.json() == {"status": "accepted"}
    user = await _user(db_factory)
    assert user.premium_until is not None
    assert abs((user.premium_until - datetime.now(UTC)) - timedelta(days=30)) < timedelta(minutes=1)

    # Notification, retour et revérification : Premium n'est pas accordé deux fois.
    checks = fake.checks
    await http.post(
        "/api/v1/payments/cinetpay/notify", data={"cpm_trans_id": tx, "cpm_site_id": SITE}
    )
    page = await http.get(f"/api/v1/payments/cinetpay/return?transaction_id={tx}")
    assert "Paiement reçu" in page.text
    assert fake.checks == checks  # déjà confirmé : plus d'appel à CinetPay
    assert (await _user(db_factory)).premium_until == user.premium_until
    async with db_factory() as session:
        kinds = list(
            await session.scalars(
                select(SubscriptionEvent.kind).where(SubscriptionEvent.user_id == user.id)
            )
        )
        notes = list(
            await session.scalars(select(Notification.kind).where(Notification.user_id == user.id))
        )
    assert kinds.count("payment") == 1
    assert notes == ["premium_paid"]
    listed = (await http.get("/api/v1/me/payments", headers=headers)).json()
    assert [p["status"] for p in listed] == ["accepted"]
    assert listed[0]["method"] == "OMCIV2"


async def test_wrong_amount_or_refusal_never_grants(
    http: AsyncClient, fake: FakeCinetPay, db_factory: Factory
) -> None:
    headers = await _signup(http)
    before = (await _user(db_factory)).premium_until
    first = (await http.post("/api/v1/payments/premium", headers=headers)).json()
    second = (await http.post("/api/v1/payments/premium", headers=headers)).json()
    fake.pay(first["transaction_id"], amount="100")  # montant trafiqué
    fake.pay(second["transaction_id"], status="REFUSED")
    for p in (first, second):
        await http.post(
            "/api/v1/payments/cinetpay/notify",
            data={"cpm_trans_id": p["transaction_id"], "cpm_site_id": SITE},
        )
    statuses = [
        (await http.get(f"/api/v1/payments/{p['id']}", headers=headers)).json()["status"]
        for p in (first, second)
    ]
    assert statuses == ["error", "refused"]
    assert (await _user(db_factory)).premium_until == before


async def test_foreign_notifications_and_payments_are_ignored(
    http: AsyncClient, fake: FakeCinetPay, db_factory: Factory
) -> None:
    owner = await _signup(http)
    other = await _signup(http, "+22997000099")
    payment = (await http.post("/api/v1/payments/premium", headers=owner)).json()
    fake.pay(payment["transaction_id"])
    wrong_site = await http.post(
        "/api/v1/payments/cinetpay/notify",
        data={"cpm_trans_id": payment["transaction_id"], "cpm_site_id": "999"},
    )
    assert wrong_site.json() == {"status": "ignored"}
    unknown = await http.post(
        "/api/v1/payments/cinetpay/notify", data={"cpm_trans_id": "FAUX", "cpm_site_id": SITE}
    )
    assert unknown.json() == {"status": "ignored"}
    assert (await http.get(f"/api/v1/payments/{payment['id']}", headers=other)).status_code == 404
    assert (await http.get("/api/v1/payments/cinetpay/notify")).status_code == 200


async def test_payment_unavailable_without_configuration(
    client: AsyncClient, db_engine: object
) -> None:
    r = await client.post("/api/v1/auth/register", json=SIGNUP)
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    refused = await client.post("/api/v1/payments/premium", headers=headers)
    assert refused.status_code == 503
    # Phrase simple pour le joueur ; le détail technique reste dans le journal du serveur.
    assert refused.json()["error"]["message"] == cinetpay.PAYMENT_DOWN


async def test_pending_payments_are_rechecked(
    http: AsyncClient, fake: FakeCinetPay, db_factory: Factory
) -> None:
    headers = await _signup(http)
    payment = (await http.post("/api/v1/payments/premium", headers=headers)).json()
    later = datetime.now(UTC) + timedelta(minutes=5)
    async with db_factory() as session:
        assert await payment_service.pending_to_check(session, later) == [payment["transaction_id"]]
        assert await payment_service.pending_to_check(session, later + timedelta(days=2)) == []
    fake.pay(payment["transaction_id"])
    async with db_factory() as session:
        done = await payment_service.confirm(session, _settings(), payment["transaction_id"])
    assert done.status == "accepted"
    async with db_factory() as session:
        assert await payment_service.pending_to_check(session, later) == []
        assert (await session.get(Payment, payment["id"])) is not None
