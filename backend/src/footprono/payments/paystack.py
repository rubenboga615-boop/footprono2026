"""Client Paystack (Côte d'Ivoire : Wave, Orange Money, MTN MoMo, cartes).

- ``init`` ouvre la page de paiement Paystack et renvoie son adresse ;
- ``check`` interroge Paystack sur l'état réel de la transaction : seule source
  de vérité (le webhook n'est qu'un signal pour vérifier, et sa signature est
  contrôlée quand même).

Montants : Paystack attend le montant multiplié par 100, y compris en francs CFA
(XOF), qui n'ont pourtant pas de centimes.
"""

import hashlib
import hmac
from typing import Any

import httpx

from footprono.core.config import Settings
from footprono.core.errors import ServiceUnavailableError
from footprono.payments.cinetpay import PAYMENT_DOWN, CheckResult

BASE_URL = "https://api.paystack.co"
TIMEOUT = 20.0
SUBUNIT = 100
CHANNELS = ["mobile_money", "card"]
# Remplacé par les tests (Paystack simulé) ; None : vrai réseau.
test_transport: httpx.AsyncBaseTransport | None = None


class PaystackClient:
    def __init__(self, secret_key: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.secret_key = secret_key
        self._transport = transport

    @classmethod
    def from_settings(
        cls, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> "PaystackClient":
        if settings.paystack_secret_key is None:
            raise ServiceUnavailableError(
                "paiement indisponible : clé Paystack absente (FP_PAYSTACK_SECRET_KEY)",
                public=PAYMENT_DOWN,
            )
        return cls(settings.paystack_secret_key.get_secret_value(), transport)

    async def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        headers = {"Authorization": f"Bearer {self.secret_key}"}
        try:
            transport = self._transport or test_transport
            async with httpx.AsyncClient(timeout=TIMEOUT, transport=transport) as client:
                response = await client.request(
                    method, f"{BASE_URL}{path}", json=body, headers=headers
                )
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                f"Paystack injoignable : {exc}", public=PAYMENT_DOWN
            ) from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise ServiceUnavailableError(
                f"réponse Paystack illisible (HTTP {response.status_code})", public=PAYMENT_DOWN
            ) from exc
        if not data.get("status"):
            raise ServiceUnavailableError(
                f"Paystack refuse : {data.get('message')} (HTTP {response.status_code})",
                public=PAYMENT_DOWN,
            )
        return data.get("data") or {}

    async def init(
        self,
        *,
        reference: str,
        amount: int,
        currency: str,
        email: str,
        callback_url: str,
        metadata: dict[str, Any],
    ) -> str:
        """Ouvre le paiement ; renvoie l'adresse de la page Paystack."""
        data = await self._call(
            "POST",
            "/transaction/initialize",
            {
                "reference": reference,
                "amount": amount * SUBUNIT,
                "currency": currency,
                "email": email,
                "callback_url": callback_url,
                "channels": CHANNELS,
                "metadata": metadata,
            },
        )
        url = data.get("authorization_url")
        if not url:
            raise ServiceUnavailableError(
                "Paystack n'a pas renvoyé de page de paiement", public=PAYMENT_DOWN
            )
        return str(url)

    async def check(self, reference: str) -> CheckResult:
        data = await self._call("GET", f"/transaction/verify/{reference}")
        provider_status = str(data.get("status") or "inconnu")
        if provider_status == "success":
            status = "accepted"
        elif provider_status in ("failed", "reversed"):
            status = "refused"
        else:  # ongoing, pending, abandoned (page fermée) : on revérifiera
            status = "pending"
        amount = data.get("amount")
        return CheckResult(
            status=status,
            provider_status=provider_status[:40],
            amount=int(amount) // SUBUNIT if isinstance(amount, int | float) else None,
            currency=data.get("currency"),
            method=(str(data.get("channel"))[:40] if data.get("channel") else None),
            raw={k: data.get(k) for k in ("id", "status", "reference", "amount", "currency",
                                          "channel", "paid_at", "gateway_response")},
        )  # fmt: skip


def valid_signature(secret_key: str, body: bytes, signature: str | None) -> bool:
    """Webhook authentique : HMAC SHA-512 du corps brut avec la clé secrète."""
    if not signature:
        return False
    expected = hmac.new(secret_key.encode(), body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)
