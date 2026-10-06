"""Paiement de Premium (Wave, Paystack, CinetPay).

- ``GET /payments/methods`` : moyens de paiement proposés (et paiement Wave manuel) ;
- ``POST /payments/premium`` : crée le paiement, renvoie l'adresse du guichet ;
- ``GET /payments/{id}`` : état (vérifié auprès du prestataire s'il est en attente) ;
- ``/payments/paystack/notify`` (webhook signé), ``/payments/cinetpay/notify`` et
  ``/payments/wave/notify`` :
  simples signaux de vérification ; ``/payments/{prestataire}/return`` : page de
  retour du client.
"""

import json
import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Form, Query, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts.plans import PREMIUM_CURRENCY, PREMIUM_DAYS, PREMIUM_PRICE
from footprono.api.deps import CurrentUserDep, RedisDep, SessionDep, SettingsDep
from footprono.core.config import Settings
from footprono.core.errors import AppError, NotFoundError
from footprono.notifications import push
from footprono.notifications import service as notifications
from footprono.payments import paystack, service
from footprono.payments.models import Payment

logger = logging.getLogger(__name__)
router = APIRouter(tags=["paiements"])


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_id: str
    amount: int
    currency: str
    days: int
    status: str
    payment_url: str | None
    method: str | None
    created_at: datetime
    paid_at: datetime | None


async def _confirm_and_notify(
    session: AsyncSession, settings: Settings, redis: RedisDep, transaction_id: str
) -> Payment:
    payment = await service.confirm(session, settings, transaction_id)
    sender = push.sender_or_none(settings)
    try:
        await notifications.publish_pending(session, redis, sender)
    finally:
        if sender is not None:
            await sender.aclose()
    return payment


class BuyIn(BaseModel):
    method: str | None = Field(None, max_length=16, examples=["wave"])


@router.get("/payments/methods")
async def payment_methods(settings: SettingsDep) -> dict[str, Any]:
    """Moyens proposés au joueur ; ``manual`` : paiement Wave sur le numéro de FootProba,
    vérifié par l'administrateur (en attendant un compte marchand)."""
    return {
        "price": PREMIUM_PRICE,
        "currency": PREMIUM_CURRENCY,
        "days": PREMIUM_DAYS,
        "methods": [
            {"id": p, "label": service.METHOD_LABELS[p]}
            for p in service.available_providers(settings)
        ],
        "manual": (
            {"wave_number": settings.wave_manual_number, "whatsapp": settings.support_whatsapp}
            if settings.wave_manual_number
            else None
        ),
    }


@router.post("/payments/premium", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def buy_premium(
    user: CurrentUserDep, session: SessionDep, settings: SettingsDep, body: BuyIn | None = None
) -> Payment:
    return await service.start_premium(
        session, settings, user, method=body.method if body else None
    )


@router.get("/me/payments", response_model=list[PaymentOut])
async def my_payments(user: CurrentUserDep, session: SessionDep) -> list[Payment]:
    rows = await session.scalars(
        select(Payment).where(Payment.user_id == user.id).order_by(Payment.id.desc()).limit(50)
    )
    return list(rows.all())


@router.get("/payments/{payment_id}", response_model=PaymentOut)
async def payment_status(
    payment_id: int,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisDep,
) -> Payment:
    payment = await session.get(Payment, payment_id)
    if payment is None or payment.user_id != user.id:
        raise NotFoundError(f"paiement {payment_id} introuvable")
    if payment.status == "pending":
        payment = await _confirm_and_notify(session, settings, redis, payment.transaction_id)
    return payment


@router.get("/payments/cinetpay/notify", include_in_schema=False)
async def notify_ping() -> dict[str, str]:
    # CinetPay vérifie que l'adresse de notification répond.
    return {"status": "ok"}


@router.post("/payments/cinetpay/notify", include_in_schema=False)
async def notify(
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisDep,
    cpm_trans_id: Annotated[str, Form()] = "",
    cpm_site_id: Annotated[str, Form()] = "",
) -> dict[str, str]:
    """Signal de CinetPay : la transaction est revérifiée auprès de CinetPay."""
    if not cpm_trans_id or cpm_site_id != (settings.cinetpay_site_id or ""):
        logger.warning("payment_notify_ignored", extra={"tx": cpm_trans_id})
        return {"status": "ignored"}
    try:
        payment = await _confirm_and_notify(session, settings, redis, cpm_trans_id)
    except AppError as exc:
        logger.warning("payment_notify_failed", extra={"tx": cpm_trans_id, "error": exc.message})
        return {"status": "ignored"}
    return {"status": payment.status}


_RETURN_PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FootProba</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#060509;
color:#f4f2f8;font-family:system-ui,sans-serif;text-align:center;padding:24px}}
h1{{color:#b793f5;font-size:22px}}p{{color:#c9c3d6;line-height:1.5}}</style></head>
<body><div><h1>{title}</h1><p>{text}</p></div></body></html>"""


@router.api_route(
    "/payments/cinetpay/return",
    methods=["GET", "POST"],
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def return_page(
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisDep,
    transaction_id: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    """Page affichée après le guichet CinetPay : l'utilisateur revient à l'application."""
    return await _return_html(session, settings, redis, transaction_id)


@router.get("/payments/paystack/return", response_class=HTMLResponse, include_in_schema=False)
async def paystack_return_page(
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisDep,
    reference: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    """Page affichée après la page de paiement Paystack (``?reference=…``)."""
    return await _return_html(session, settings, redis, reference)


@router.post("/payments/paystack/notify", include_in_schema=False)
async def paystack_notify(
    request: Request, session: SessionDep, settings: SettingsDep, redis: RedisDep
) -> dict[str, str]:
    """Webhook Paystack : signature HMAC SHA-512 contrôlée, puis la transaction est
    revérifiée auprès de Paystack (le contenu du message n'est jamais cru tel quel)."""
    body = await request.body()
    secret = settings.paystack_secret_key
    signature = request.headers.get("x-paystack-signature")
    if secret is None or not paystack.valid_signature(secret.get_secret_value(), body, signature):
        logger.warning("paystack_notify_bad_signature")
        return {"status": "ignored"}
    try:
        event = json.loads(body)
        reference = str(event["data"]["reference"])
    except (ValueError, KeyError, TypeError):
        return {"status": "ignored"}
    if event.get("event") != "charge.success":
        return {"status": "ignored"}
    try:
        payment = await _confirm_and_notify(session, settings, redis, reference)
    except AppError as exc:
        logger.warning("payment_notify_failed", extra={"tx": reference, "error": exc.message})
        return {"status": "ignored"}
    return {"status": payment.status}


@router.get("/payments/wave/return", response_class=HTMLResponse, include_in_schema=False)
async def wave_return_page(
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisDep,
    transaction_id: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    """Page affichée au retour de l'application Wave (succès ou échec)."""
    return await _return_html(session, settings, redis, transaction_id)


@router.post("/payments/wave/notify", include_in_schema=False)
async def wave_notify(
    request: Request, session: SessionDep, settings: SettingsDep, redis: RedisDep
) -> dict[str, str]:
    """Webhook Wave : simple signal. La session est revérifiée auprès de Wave avec notre
    clé (montant, devise, état) ; le contenu du message n'est jamais cru tel quel."""
    try:
        event = json.loads(await request.body())
        reference = str(event["data"]["client_reference"])
    except (ValueError, KeyError, TypeError):
        return {"status": "ignored"}
    try:
        payment = await _confirm_and_notify(session, settings, redis, reference)
    except AppError as exc:
        logger.warning("payment_notify_failed", extra={"tx": reference, "error": exc.message})
        return {"status": "ignored"}
    return {"status": payment.status}


async def _return_html(
    session: AsyncSession, settings: Settings, redis: RedisDep, transaction_id: str | None
) -> HTMLResponse:
    title, text = (
        "Paiement en cours de vérification",
        (
            "Retourne dans l'application FootProba : ton abonnement s'affiche dès que "
            "le paiement est confirmé."
        ),
    )
    if transaction_id:
        try:
            payment = await _confirm_and_notify(session, settings, redis, transaction_id)
        except AppError:
            payment = None
        if payment is not None and payment.status == "accepted":
            title, text = (
                "Paiement reçu",
                "Premium est activé. Retourne dans l'application FootProba.",
            )
        elif payment is not None and payment.status == "refused":
            title, text = (
                "Paiement refusé",
                "Aucun montant n'a été débité. Tu peux réessayer depuis l'application.",
            )
    return HTMLResponse(_RETURN_PAGE.format(title=title, text=text))
