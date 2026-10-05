"""Connexion avec Google (Firebase Authentication).

L'application connecte le joueur à Google par Firebase, puis envoie au serveur le
jeton d'identité Firebase. Le serveur le vérifie lui-même (signature RS256 avec
les certificats publics de Google, projet, émetteur, expiration) : seul un jeton
valide et récent ouvre une session. Aucun secret n'est nécessaire.
"""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from cryptography.x509 import load_pem_x509_certificate

from footprono.accounts.service import UnauthorizedError
from footprono.core.config import Settings
from footprono.core.errors import ServiceUnavailableError

CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
)
GOOGLE_DOWN = "Connexion Google momentanément indisponible. Utilise ton numéro."
# Remplacé par les tests (certificats d'essai) ; None : certificats de Google.
certificate_source: Callable[[], Awaitable[dict[str, str]]] | None = None
_cache: dict[str, Any] = {"certs": {}, "until": 0.0}


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str  # identifiant Google stable
    email: str
    name: str


async def _download() -> dict[str, str]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(CERTS_URL)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ServiceUnavailableError(
            f"certificats Google injoignables : {exc}", public=GOOGLE_DOWN
        ) from exc
    max_age = 3600
    for part in response.headers.get("cache-control", "").split(","):
        if part.strip().startswith("max-age="):
            max_age = int(part.strip()[8:])
    _cache["until"] = time.time() + max_age
    certs: dict[str, str] = response.json()
    return certs


async def _certificates(refresh: bool = False) -> dict[str, str]:
    if certificate_source is not None:
        return await certificate_source()
    if refresh or time.time() >= _cache["until"] or not _cache["certs"]:
        _cache["certs"] = await _download()
    certs: dict[str, str] = _cache["certs"]
    return certs


async def verify(settings: Settings, token: str) -> GoogleIdentity:
    project = settings.firebase_project_id
    if not project:
        raise ServiceUnavailableError("FP_FIREBASE_PROJECT_ID non défini", public=GOOGLE_DOWN)
    refused = UnauthorizedError("connexion Google refusée : réessaie")
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError:
        raise refused from None
    certs = await _certificates()
    if kid not in certs:  # Google a changé de clés : nouvelle liste, une fois
        certs = await _certificates(refresh=True)
    if kid not in certs:
        raise refused
    key = load_pem_x509_certificate(certs[kid].encode()).public_key()
    try:
        claims = jwt.decode(
            token,
            key,  # type: ignore[arg-type]
            algorithms=["RS256"],
            audience=project,
            issuer=f"https://securetoken.google.com/{project}",
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            leeway=60,
        )
    except jwt.PyJWTError:
        raise refused from None
    firebase = claims.get("firebase") or {}
    google_ids = (firebase.get("identities") or {}).get("google.com") or []
    email = claims.get("email")
    if firebase.get("sign_in_provider") != "google.com" or not google_ids or not email:
        raise refused
    if claims.get("email_verified") is not True:
        raise UnauthorizedError("adresse Google non vérifiée")
    name = str(claims.get("name") or email.split("@")[0]).strip()[:40]
    return GoogleIdentity(sub=str(google_ids[0]), email=str(email).lower(), name=name)
