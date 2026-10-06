"""Client Wave Checkout (Côte d'Ivoire, Sénégal : paiement depuis l'application Wave).

- ``init`` crée une session de paiement et renvoie son adresse (``wave_launch_url``),
  qui ouvre l'application Wave du joueur ;
- ``check`` retrouve la session par notre référence (``client_reference``) et lit son
  état chez Wave : seule source de vérité. Le webhook n'est qu'un signal pour vérifier ;
  son contenu n'est jamais cru tel quel.

Clé : compte Wave Business, clé d'API « Checkout » (secrète). Montants en francs CFA
entiers, envoyés comme texte (« 2000 »).
"""

from typing import Any

import httpx

from footprono.core.config import Settings
from footprono.core.errors import ServiceUnavailableError
from footprono.payments.cinetpay import PAYMENT_DOWN, CheckResult

BASE_URL = "https://api.wave.com"
TIMEOUT = 20.0
# Remplacé par les tests (Wave simulé) ; None : vrai réseau.
test_transport: httpx.AsyncBaseTransport | None = None


class WaveClient:
    def __init__(self, api_key: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.api_key = api_key
        self._transport = transport

    @classmethod
    def from_settings(
        cls, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> "WaveClient":
        if settings.wave_api_key is None:
            raise ServiceUnavailableError(
                "paiement indisponible : clé Wave absente (FP_WAVE_API_KEY)", public=PAYMENT_DOWN
            )
        return cls(settings.wave_api_key.get_secret_value(), transport)

    async def _call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            transport = self._transport or test_transport
            async with httpx.AsyncClient(timeout=TIMEOUT, transport=transport) as client:
                response = await client.request(
                    method, f"{BASE_URL}{path}", json=body, params=params, headers=headers
                )
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(f"Wave injoignable : {exc}", public=PAYMENT_DOWN) from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise ServiceUnavailableError(
                f"réponse Wave illisible (HTTP {response.status_code})", public=PAYMENT_DOWN
            ) from exc
        if response.status_code >= 400:
            message = data.get("message") if isinstance(data, dict) else None
            raise ServiceUnavailableError(
                f"Wave refuse : {message or data} (HTTP {response.status_code})",
                public=PAYMENT_DOWN,
            )
        return data

    async def init(
        self,
        *,
        client_reference: str,
        amount: int,
        currency: str,
        success_url: str,
        error_url: str,
    ) -> str:
        """Ouvre une session de paiement ; renvoie l'adresse qui lance l'application Wave."""
        data = await self._call(
            "POST",
            "/v1/checkout/sessions",
            {
                "amount": str(amount),
                "currency": currency,
                "client_reference": client_reference,
                "success_url": success_url,
                "error_url": error_url,
            },
        )
        url = data.get("wave_launch_url") if isinstance(data, dict) else None
        if not url:
            raise ServiceUnavailableError(
                "Wave n'a pas renvoyé de page de paiement", public=PAYMENT_DOWN
            )
        return str(url)

    async def check(self, client_reference: str) -> CheckResult:
        data = await self._call(
            "GET", "/v1/checkout/sessions/search", params={"client_reference": client_reference}
        )
        sessions = data.get("result", []) if isinstance(data, dict) else data
        mine = [s for s in sessions or [] if s.get("client_reference") == client_reference]
        if not mine:
            return CheckResult(status="pending", provider_status="introuvable", amount=None,
                               currency=None, method=None, raw={})  # fmt: skip
        # La session payée, s'il y en a une ; sinon la plus récente.
        paid = [s for s in mine if s.get("payment_status") == "succeeded"]
        found = paid[0] if paid else mine[-1]
        payment_status = str(found.get("payment_status") or "inconnu")
        checkout_status = str(found.get("checkout_status") or "")
        if payment_status == "succeeded":
            status = "accepted"
        elif payment_status == "cancelled" or checkout_status == "expired":
            status = "refused"
        else:  # processing, session encore ouverte : on revérifiera
            status = "pending"
        try:
            amount: int | None = int(float(str(found.get("amount"))))
        except ValueError:
            amount = None
        return CheckResult(
            status=status,
            provider_status=f"{payment_status}/{checkout_status}"[:40],
            amount=amount,
            currency=found.get("currency"),
            method="wave",
            raw={k: found.get(k) for k in ("id", "payment_status", "checkout_status", "amount",
                                           "currency", "client_reference", "transaction_id",
                                           "when_completed")},
        )  # fmt: skip
