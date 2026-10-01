"""Mots de passe (scrypt, bibliothèque standard) et jetons d'accès (JWT HS256)."""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from footprono.core.config import Settings
from footprono.core.errors import ServiceUnavailableError

_N, _R, _P = 2**14, 8, 1
_MIN_SECRET = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    salt_b64, digest_b64 = base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    return f"scrypt${_N}${_R}${_P}${salt_b64}${digest_b64}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    candidate = hashlib.scrypt(
        password.encode(),
        salt=base64.b64decode(salt),
        n=int(n),
        r=int(r),
        p=int(p),
        dklen=len(base64.b64decode(digest)),
    )
    return hmac.compare_digest(candidate, base64.b64decode(digest))


def _secret(settings: Settings) -> str:
    secret = settings.secret_key.get_secret_value() if settings.secret_key else ""
    if len(secret) < _MIN_SECRET:
        raise ServiceUnavailableError(
            "FP_SECRET_KEY absente ou trop courte : connexion impossible "
            "(relancer scripts/termux/setup.sh, qui la génère)"
        )
    return secret


def create_access_token(user_id: int, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(days=settings.access_token_days),
    }
    return jwt.encode(payload, _secret(settings), algorithm="HS256")


def read_access_token(token: str, settings: Settings) -> int | None:
    """Identifiant de l'utilisateur, ou None si le jeton est invalide ou expiré."""
    try:
        payload = jwt.decode(token, _secret(settings), algorithms=["HS256"])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
