"""Code de sécurité à 6 chiffres de la console (TOTP, RFC 6238).

Compatible avec Google Authenticator, Microsoft Authenticator, Authy… : clé de
20 octets, code de 6 chiffres renouvelé toutes les 30 secondes. La clé est
gardée chiffrée en base (Fernet, clé dérivée de FP_SECRET_KEY) ; un code déjà
utilisé est refusé (rejeu).
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken

from footprono.core.config import Settings

STEP = 30
DIGITS = 6
ISSUER = "FootProba Console"


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    return base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))


def code_at(secret: str, counter: int) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


def current_counter(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP)


def matching_counter(secret: str, code: str, now: float | None = None) -> int | None:
    """Pas de temps du code (± 30 s de décalage d'horloge toléré), sinon None."""
    code = "".join(c for c in code if c.isdigit())
    if len(code) != DIGITS:
        return None
    counter = current_counter(now)
    for candidate in (counter, counter - 1, counter + 1):
        if hmac.compare_digest(code_at(secret, candidate), code):
            return candidate
    return None


def uri(secret: str, account: str) -> str:
    """Lien « otpauth:// » : ouvre directement l'application d'authentification."""
    label = quote(f"{ISSUER}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}&digits=6&period=30"


def _fernet(settings: Settings) -> Fernet:
    raw = settings.secret_key.get_secret_value() if settings.secret_key else ""
    key = hashlib.sha256(("totp:" + raw).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def seal(settings: Settings, secret: str) -> str:
    return _fernet(settings).encrypt(secret.encode()).decode()


def unseal(settings: Settings, sealed: str) -> str | None:
    try:
        return _fernet(settings).decrypt(sealed.encode()).decode()
    except InvalidToken:
        return None
