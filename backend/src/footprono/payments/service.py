"""Achat de Premium : création du paiement, puis confirmation vérifiée.

Premium n'est accordé que si CinetPay confirme la transaction **et** que le
montant et la devise sont ceux attendus. La confirmation est idempotente :
notification CinetPay, retour de l'utilisateur et vérification périodique
peuvent tous la déclencher, Premium n'est accordé qu'une fois.
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts import admin
from footprono.accounts.models import User
from footprono.accounts.plans import PREMIUM_CURRENCY, PREMIUM_DAYS, PREMIUM_PRICE
from footprono.core.config import Settings
from footprono.core.errors import NotFoundError, ServiceUnavailableError
from footprono.notifications import service as notifications
from footprono.payments.cinetpay import CinetPayClient
from footprono.payments.models import Payment

logger = logging.getLogger(__name__)
PROVIDER = "cinetpay"
# Un paiement non confirmé après ce délai n'est plus vérifié automatiquement.
RECONCILE_WINDOW = timedelta(hours=24)


def _urls(settings: Settings) -> tuple[str, str]:
    if not settings.public_url:
        raise ServiceUnavailableError(
            "paiement indisponible : adresse publique du serveur (FP_PUBLIC_URL) non définie"
        )
    base = settings.public_url.rstrip("/") + settings.api_prefix
    return f"{base}/payments/cinetpay/notify", f"{base}/payments/cinetpay/return"


async def start_premium(
    session: AsyncSession,
    settings: Settings,
    user: User,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Payment:
    client = CinetPayClient.from_settings(settings, transport)
    notify_url, return_url = _urls(settings)
    payment = Payment(
        user_id=user.id,
        provider=PROVIDER,
        transaction_id=f"FP{user.id}T{secrets.token_hex(8).upper()}",
        amount=PREMIUM_PRICE,
        currency=PREMIUM_CURRENCY,
        days=PREMIUM_DAYS,
        status="pending",
        raw={},
    )
    session.add(payment)
    await session.flush()
    payment.payment_url = await client.init(
        transaction_id=payment.transaction_id,
        amount=payment.amount,
        currency=payment.currency,
        description=f"FootProno Premium {PREMIUM_DAYS} jours",
        notify_url=notify_url,
        # CinetPay revient sur cette page ; elle vérifie aussitôt le paiement.
        return_url=f"{return_url}?transaction_id={payment.transaction_id}",
    )
    await session.commit()
    return payment


async def confirm(
    session: AsyncSession,
    settings: Settings,
    transaction_id: str,
    transport: httpx.AsyncBaseTransport | None = None,
    now: datetime | None = None,
) -> Payment:
    """Vérifie la transaction auprès de CinetPay et accorde Premium une seule fois."""
    payment = await session.scalar(
        select(Payment).where(Payment.transaction_id == transaction_id).with_for_update()
    )
    if payment is None:
        raise NotFoundError(f"paiement {transaction_id} inconnu")
    if payment.status != "pending":
        return payment
    result = await CinetPayClient.from_settings(settings, transport).check(transaction_id)
    payment.provider_status, payment.method = result.provider_status, result.method
    payment.raw = result.raw
    if result.status == "accepted":
        if result.amount != payment.amount or result.currency != payment.currency:
            payment.status = "error"
            logger.error(
                "payment_amount_mismatch",
                extra={"tx": transaction_id, "amount": result.amount, "currency": result.currency},
            )
        else:
            now = now or datetime.now(UTC)
            user = await session.get(User, payment.user_id)
            assert user is not None
            payment.status, payment.paid_at = "accepted", now
            await admin.grant_premium(
                session, None, user, payment.days, note=f"CinetPay {transaction_id}",
                now=now, kind="payment",
            )  # fmt: skip
            assert user.premium_until is not None
            notifications.add(
                session, user.id, "premium_paid", "Premium activé",
                f"Paiement de {notifications.money(payment.amount, payment.currency)} reçu. "
                f"Premium jusqu'au {user.premium_until:%d/%m/%Y}.",
                {"payment_id": payment.id},
            )  # fmt: skip
    elif result.status == "refused":
        payment.status = "refused"
    await session.commit()
    return payment


async def pending_to_check(session: AsyncSession, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(UTC)
    rows = await session.scalars(
        select(Payment.transaction_id).where(
            Payment.status == "pending",
            Payment.created_at >= now - RECONCILE_WINDOW,
            Payment.created_at <= now - timedelta(minutes=2),
        )
    )
    return list(rows.all())
