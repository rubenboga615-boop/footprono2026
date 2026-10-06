"""Notifications sur le téléphone fermé : Firebase Cloud Messaging (API HTTP v1).

Activé seulement si ``FP_FCM_CREDENTIALS_FILE`` désigne la clé du compte de
service du projet Firebase (fichier JSON, secret, jamais dans le dépôt). Sans
clé, rien n'est envoyé et l'état est affiché tel quel (``status()``) : les
notifications restent visibles dans l'application.

Un jeton refusé par Firebase (application désinstallée, jeton périmé) est
supprimé : il ne servira plus.
"""

import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import jwt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.core.config import Settings
from footprono.notifications.models import Notification, PushDevice

logger = logging.getLogger(__name__)
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
SEND_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
# Canal Android créé par l'application (son, importance haute).
ANDROID_CHANNEL = "footprono"
TIMEOUT = 15.0
JWT_BEARER = "urn:ietf:params:oauth:grant-type:jwt-bearer"


class PushConfigError(RuntimeError):
    """Clé du compte de service absente, illisible ou incomplète."""


@dataclass(frozen=True)
class ServiceAccount:
    project_id: str
    client_email: str
    private_key: str
    token_uri: str

    @classmethod
    def load(cls, path: Path) -> "ServiceAccount":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PushConfigError(f"clé Firebase illisible ({path}) : {exc}") from exc
        if raw.get("type") != "service_account":
            raise PushConfigError(
                f"{path} n'est pas une clé de compte de service "
                "(Paramètres du projet → Comptes de service → Générer une nouvelle clé privée)"
            )
        missing = [k for k in ("project_id", "client_email", "private_key") if not raw.get(k)]
        if missing:
            raise PushConfigError(f"clé Firebase incomplète : {', '.join(missing)} manquant")
        return cls(
            project_id=raw["project_id"],
            client_email=raw["client_email"],
            private_key=raw["private_key"],
            token_uri=raw.get("token_uri") or "https://oauth2.googleapis.com/token",
        )


@dataclass
class SendResult:
    sent: int = 0
    removed: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {"sent": self.sent, "removed": self.removed, "failed": self.failed}


def _stringify(data: dict[str, Any]) -> dict[str, str]:
    # FCM n'accepte que des chaînes dans « data ».
    return {k: v if isinstance(v, str) else json.dumps(v, default=str) for k, v in data.items()}


def _token_is_dead(response: httpx.Response) -> bool:
    """Jeton à oublier : appareil désinscrit ou jeton invalide (doc FCM v1)."""
    if response.status_code == 404:
        return True
    if response.status_code != 400:
        return False
    try:
        error = response.json().get("error", {})
    except ValueError:
        return False
    codes = {d.get("errorCode") for d in error.get("details", []) if isinstance(d, dict)}
    return "UNREGISTERED" in codes or (
        "INVALID_ARGUMENT" in codes and "registration token" in str(error.get("message", ""))
    )


class FcmSender:
    def __init__(
        self,
        account: ServiceAccount,
        client: httpx.AsyncClient | None = None,
        web_link: str | None = None,
    ) -> None:
        self.account = account
        self._client = client
        # Version web (iPhone, ordinateur) : page ouverte en touchant la notification.
        self.web_link = web_link
        self._access_token: str | None = None
        self._expires_at = 0.0

    @classmethod
    def from_settings(cls, settings: Settings) -> "FcmSender | None":
        """None si aucune clé n'est configurée ; erreur si la clé est inutilisable."""
        if settings.fcm_credentials_file is None:
            return None
        link = settings.public_url.rstrip("/") + "/app/" if settings.public_url else None
        return cls(ServiceAccount.load(settings.fcm_credentials_file), web_link=link)

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=TIMEOUT)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def access_token(self) -> str:
        """Jeton OAuth2 Google (1 h), obtenu en signant une assertion avec la clé privée."""
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        now = int(time.time())
        assertion = jwt.encode(
            {
                "iss": self.account.client_email,
                "scope": SCOPE,
                "aud": self.account.token_uri,
                "iat": now,
                "exp": now + 3600,
            },
            self.account.private_key,
            algorithm="RS256",
        )
        client = await self._http()
        response = await client.post(
            self.account.token_uri,
            data={"grant_type": JWT_BEARER, "assertion": assertion},
        )
        if response.status_code != 200:
            raise PushConfigError(
                f"Google refuse la clé Firebase ({response.status_code}) : {response.text[:300]}"
            )
        body = response.json()
        self._access_token = str(body["access_token"])
        self._expires_at = now + float(body.get("expires_in", 3600))
        return self._access_token

    async def send_one(
        self, token: str, title: str, body: str, data: dict[str, Any]
    ) -> httpx.Response:
        client = await self._http()
        message = {
            "token": token,
            "notification": {"title": title, "body": body},
            "data": _stringify(data),
            "android": {"priority": "high", "notification": {"channel_id": ANDROID_CHANNEL}},
        }
        if self.web_link:
            message["webpush"] = {
                "fcm_options": {"link": self.web_link},
                "notification": {"icon": f"{self.web_link}icons/Icon-192.png"},
            }
        return await client.post(
            SEND_URL.format(project=self.account.project_id),
            headers={"Authorization": f"Bearer {await self.access_token()}"},
            json={"message": message},
        )

    async def send_to_user(
        self,
        session: AsyncSession,
        user_id: int,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> SendResult:
        result = SendResult()
        devices = (
            await session.scalars(select(PushDevice).where(PushDevice.user_id == user_id))
        ).all()
        dead: list[int] = []
        for device in devices:
            try:
                response = await self.send_one(device.token, title, body, data or {})
            except httpx.HTTPError as exc:
                logger.warning("push_failed", extra={"device": device.id, "error": str(exc)})
                result.failed += 1
                continue
            if response.status_code == 200:
                result.sent += 1
            elif _token_is_dead(response):
                dead.append(device.id)
            else:
                logger.warning(
                    "push_rejected",
                    extra={
                        "device": device.id,
                        "status": response.status_code,
                        "body": response.text[:300],
                    },
                )
                result.failed += 1
        if dead:
            await session.execute(delete(PushDevice).where(PushDevice.id.in_(dead)))
            await session.commit()
            result.removed = len(dead)
        return result

    async def send_notifications(
        self, session: AsyncSession, notes: Sequence[Notification]
    ) -> SendResult:
        total = SendResult()
        for note in notes:
            data = {**note.data, "notification_id": note.id, "kind": note.kind}
            try:
                r = await self.send_to_user(session, note.user_id, note.title, note.body, data)
            except PushConfigError as exc:
                logger.error("push_config_error", extra={"error": str(exc)})
                total.failed += 1
                continue
            total.sent += r.sent
            total.removed += r.removed
            total.failed += r.failed
        return total


def sender_or_none(settings: Settings) -> FcmSender | None:
    """Expéditeur Firebase, ou None (non configuré, ou clé inutilisable : consigné)."""
    try:
        return FcmSender.from_settings(settings)
    except PushConfigError as exc:
        logger.error("push_disabled", extra={"error": str(exc)})
        return None


def status(settings: Settings) -> dict[str, Any]:
    """État affichable des notifications push (sans secret)."""
    if settings.fcm_credentials_file is None:
        return {"enabled": False, "reason": "FP_FCM_CREDENTIALS_FILE non défini"}
    try:
        account = ServiceAccount.load(settings.fcm_credentials_file)
    except PushConfigError as exc:
        return {"enabled": False, "reason": str(exc)}
    return {"enabled": True, "project_id": account.project_id}
