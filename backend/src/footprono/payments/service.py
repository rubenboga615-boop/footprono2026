"""Achat de Premium : création du paiement, puis confirmation vérifiée.

Prestataires : Wave, Paystack, CinetPay, selon les clés configurées ; le joueur
choisit quand il y en a plusieurs (sinon le premier). Un paiement est toujours
vérifié auprès du prestataire qui l'a créé. Premium n'est accordé
que si le prestataire confirme la transaction **et** que le montant et la devise
sont ceux attendus. La confirmation est idempotente : notification (webhook),
retour de l'utilisateur et vérification périodique peuvent tous la déclencher,
Premium n'est accordé qu'une fois.
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
from footprono.payments.cinetpay import PAYMENT_DOWN, CheckResult, CinetPayClient
from footprono.payments.models import Payment
from footprono.payments.paystack import PaystackClient
from footprono.payments.wave import WaveClient

logger = logging.getLogger(__name__)
PROVIDER = "cinetpay"
PROVIDER_NAMES = {"cinetpay": "CinetPay", "paystack": "Paystack", "wave": "Wave"}
# Ce que le joueur voit pour chaque prestataire.
METHOD_LABELS = {
    "wave": "Wave",
    "paystack": "Orange Money, MTN, Wave ou carte",
    "cinetpay": "Orange Money, MTN, Moov ou Wave",
}


def available_providers(settings: Settings) -> list[str]:
    """Prestataires configurés, dans l'ordre proposé (Wave d'abord : 1 % de frais)."""
    out = []
    if settings.wave_api_key is not None:
        out.append("wave")
    if settings.paystack_secret_key is not None:
        out.append("paystack")
    if settings.cinetpay_api_key is not None:
        out.append("cinetpay")
    return out


def active_provider(settings: Settings, wanted: str | None = None) -> str:
    providers = available_providers(settings)
    if wanted is not None and wanted in providers:
        return wanted
    return providers[0] if providers else PROVIDER


async def _check(
    settings: Settings, payment: Payment, transport: httpx.AsyncBaseTransport | None
) -> CheckResult:
    if payment.provider == "wave":
        return await WaveClient.from_settings(settings, transport).check(payment.transaction_id)
    if payment.provider == "paystack":
        return await PaystackClient.from_settings(settings, transport).check(payment.transaction_id)
    return await CinetPayClient.from_settings(settings, transport).check(payment.transaction_id)


# Un paiement non confirmé après ce délai n'est plus vérifié automatiquement.
RECONCILE_WINDOW = timedelta(hours=24)


def _urls(settings: Settings, provider: str = PROVIDER) -> tuple[str, str]:
    if not settings.public_url:
        raise ServiceUnavailableError(
            "paiement indisponible : adresse publique du serveur (FP_PUBLIC_URL) non définie",
            public=PAYMENT_DOWN,
        )
    base = settings.public_url.rstrip("/") + settings.api_prefix
    return f"{base}/payments/{provider}/notify", f"{base}/payments/{provider}/return"


def _email(settings: Settings, user: User) -> str:
    """Paystack exige une adresse : celle du compte Google, sinon une adresse
    technique propre au compte (aucune donnée personnelle)."""
    if user.email:
        return user.email
    host = (settings.public_url or "footproba.app").split("//")[-1].split("/")[0]
    return f"joueur{user.id}@{host}"


async def start_premium(
    session: AsyncSession,
    settings: Settings,
    user: User,
    transport: httpx.AsyncBaseTransport | None = None,
    method: str | None = None,
) -> Payment:
    provider = active_provider(settings, method)
    notify_url, return_url = _urls(settings, provider)
    payment = Payment(
        user_id=user.id,
        provider=provider,
        transaction_id=f"FP{user.id}T{secrets.token_hex(8).upper()}",
        amount=PREMIUM_PRICE,
        currency=PREMIUM_CURRENCY,
        days=PREMIUM_DAYS,
        status="pending",
        raw={},
    )
    if provider == "wave":
        wave = WaveClient.from_settings(settings, transport)
        session.add(payment)
        await session.flush()
        # Wave revient sur cette page (succès ou échec) ; elle vérifie aussitôt.
        back = f"{return_url}?transaction_id={payment.transaction_id}"
        payment.payment_url = await wave.init(
            client_reference=payment.transaction_id,
            amount=payment.amount,
            currency=payment.currency,
            success_url=back,
            error_url=back,
        )
        await session.commit()
        return payment
    if provider == "paystack":
        client = PaystackClient.from_settings(settings, transport)
        session.add(payment)
        await session.flush()
        # Paystack revient sur cette page avec ?reference=… ; elle vérifie aussitôt.
        payment.payment_url = await client.init(
            reference=payment.transaction_id,
            amount=payment.amount,
            currency=payment.currency,
            email=_email(settings, user),
            callback_url=return_url,
            metadata={"payment_id": payment.id, "offer": f"Premium {PREMIUM_DAYS} jours"},
        )
        await session.commit()
        return payment
    cinetpay = CinetPayClient.from_settings(settings, transport)
    session.add(payment)
    await session.flush()
    payment.payment_url = await cinetpay.init(
        transaction_id=payment.transaction_id,
        amount=payment.amount,
        currency=payment.currency,
        description=f"FootProba Premium {PREMIUM_DAYS} jours",
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
    """Vérifie la transaction auprès de son prestataire et accorde Premium une seule fois."""
    payment = await session.scalar(
        select(Payment).where(Payment.transaction_id == transaction_id).with_for_update()
    )
    if payment is None:
        raise NotFoundError(f"paiement {transaction_id} inconnu")
    if payment.status != "pending":
        return payment
    result = await _check(settings, payment, transport)
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
            label = PROVIDER_NAMES.get(payment.provider, payment.provider)
            await admin.grant_premium(
                session, None, user, payment.days, note=f"{label} {transaction_id}",
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
