"""Fichiers produits par les actions de la console (exports, rapports, archives).

Rangés à plat dans ``FP_CONSOLE_FILES_DIR`` et gardés ``KEEP_DAYS`` jours ; les
sous-dossiers servent de caches aux actions et ne sont pas listés. Jamais de
donnée personnelle : les sauvegardes de la base restent hors de ce dossier.

Téléchargement par lien signé de courte durée (``download_link``) : le navigateur
télécharge directement le fichier, sans le charger en mémoire, et le lien ne sert
plus après ``LINK_SECONDS``.
"""

import hashlib
import hmac
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from footprono.core.config import Settings
from footprono.core.errors import ForbiddenError, NotFoundError

KEEP_DAYS = 30
LINK_SECONDS = 300
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")


def files_dir(settings: Settings) -> Path:
    path = settings.console_files_dir.expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_path(settings: Settings, name: str) -> Path:
    """Fichier du dossier de la console ; tout autre chemin est refusé."""
    if not _NAME.match(name):
        raise NotFoundError("fichier introuvable")
    path = files_dir(settings) / name
    if not path.is_file():
        raise NotFoundError("fichier introuvable")
    return path


def cleanup(settings: Settings, now: datetime | None = None) -> int:
    limit = (now or datetime.now(UTC)) - timedelta(days=KEEP_DAYS)
    removed = 0
    for path in files_dir(settings).iterdir():
        if path.is_file() and datetime.fromtimestamp(path.stat().st_mtime, UTC) < limit:
            path.unlink()
            removed += 1
    return removed


def list_files(settings: Settings) -> list[dict[str, Any]]:
    cleanup(settings)
    out = []
    for path in files_dir(settings).iterdir():
        if path.is_file() and _NAME.match(path.name) and not path.name.endswith(".part"):
            stat = path.stat()
            out.append(
                {
                    "name": path.name,
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC),
                }
            )
    return sorted(out, key=lambda f: f["modified_at"], reverse=True)


def _signature(settings: Settings, name: str, expires: int) -> str:
    secret = settings.secret_key.get_secret_value() if settings.secret_key else "dev"
    return hmac.new(secret.encode(), f"{name}|{expires}".encode(), hashlib.sha256).hexdigest()


def download_link(settings: Settings, prefix: str, name: str) -> str:
    safe_path(settings, name)
    expires = int(time.time()) + LINK_SECONDS
    return f"{prefix}/{name}?expires={expires}&signature={_signature(settings, name, expires)}"


def check_link(settings: Settings, name: str, expires: int, signature: str) -> Path:
    if expires < time.time() or not hmac.compare_digest(
        signature, _signature(settings, name, expires)
    ):
        raise ForbiddenError("lien de téléchargement expiré : en demander un nouveau")
    return safe_path(settings, name)
