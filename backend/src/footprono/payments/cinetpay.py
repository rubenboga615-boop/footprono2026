"""Client CinetPay (API de paiement v2) : Orange Money, MTN MoMo, Moov Money, Wave…

- ``init`` crée le guichet de paiement et renvoie son adresse (``payment_url``),
  ouverte par l'application dans le navigateur ;
- ``check`` interroge CinetPay sur l'état réel d'une transaction. C'est la
  seule source de vérité : une notification reçue n'est qu'un signal pour
  vérifier (elle pourrait être forgée).
"""

from dataclasses import dataclass
from typing import Any

import httpx

from footprono.core.config import Settings
from footprono.core.errors import ServiceUnavailableError

BASE_URL = "https://api-checkout.cinetpay.com/v2"
TIMEOUT = 20.0
# Remplacé par les tests (CinetPay simulé) ; None : vrai réseau.
test_transport: httpx.AsyncBaseTransport | None = None


@dataclass(frozen=True)
class CheckResult:
    status: str  # accepted, refused, pending
    provider_status: str
    amount: int | None
    currency: str | None
    method: str | None
    raw: dict[str, Any]


class CinetPayClient:
    def __init__(
        self, api_key: str, site_id: str, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.api_key = api_key
        self.site_id = site_id
        self._transport = transport

    @classmethod
    def from_settings(
        cls, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> "CinetPayClient":
        if settings.cinetpay_api_key is None or settings.cinetpay_site_id is None:
            raise ServiceUnavailableError(
                "paiement indisponible : CinetPay n'est pas encore configuré sur le serveur"
            )
        return cls(
            settings.cinetpay_api_key.get_secret_value(), settings.cinetpay_site_id, transport
        )

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {"apikey": self.api_key, "site_id": self.site_id, **payload}
        try:
            transport = self._transport or test_transport
            async with httpx.AsyncClient(timeout=TIMEOUT, transport=transport) as client:
                response = await client.post(f"{BASE_URL}{path}", json=body)
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(f"CinetPay injoignable : {exc}") from exc
        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise ServiceUnavailableError(
                f"réponse CinetPay illisible (HTTP {response.status_code})"
            ) from exc
        return data

    async def init(
        self,
        *,
        transaction_id: str,
        amount: int,
        currency: str,
        description: str,
        notify_url: str,
        return_url: str,
    ) -> str:
        """Crée le paiement ; renvoie l'adresse du guichet CinetPay."""
        data = await self._post(
            "/payment",
            {
                "transaction_id": transaction_id,
                "amount": amount,
                "currency": currency,
                "description": description,
                "notify_url": notify_url,
                "return_url": return_url,
                "channels": "ALL",
                "lang": "fr",
            },
        )
        url = (data.get("data") or {}).get("payment_url")
        if str(data.get("code")) != "201" or not url:
            raise ServiceUnavailableError(
                f"CinetPay refuse le paiement : {data.get('message') or data.get('description')}"
                f" (code {data.get('code')})"
            )
        return str(url)

    async def check(self, transaction_id: str) -> CheckResult:
        data = await self._post("/payment/check", {"transaction_id": transaction_id})
        info = data.get("data") or {}
        provider_status = str(info.get("status") or data.get("message") or data.get("code"))
        if str(data.get("code")) == "00" and info.get("status") == "ACCEPTED":
            status = "accepted"
        elif info.get("status") == "REFUSED":
            status = "refused"
        else:  # en attente du client, en cours, inconnu : on revérifiera
            status = "pending"
        amount = info.get("amount")
        return CheckResult(
            status=status,
            provider_status=provider_status[:40],
            amount=int(float(amount)) if amount not in (None, "") else None,
            currency=info.get("currency"),
            method=(info.get("payment_method") or None),
            raw=data,
        )
