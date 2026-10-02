"""Version de l'application Android distribuée par le serveur (hors Play Store).

Publier (sur le serveur) : ``footprono-admin publish-apk footprono-apk.zip
--notes "…"`` avec l'archive téléchargée depuis GitHub Actions. Le fichier
``release.json`` de l'archive donne le numéro de construction ; l'APK arm64
(téléphones Android de 2017 et après) est copié dans ``FP_APP_RELEASE_DIR``.

L'application compare son numéro (``--dart-define=FP_BUILD``) à
``GET /app/version`` et propose la mise à jour ; sous ``minimum_build``, la
mise à jour est obligatoire (correctif de sécurité, API incompatible).
"""

import hashlib
import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from footprono.core.errors import AppError

APK_IN_ZIP = "app-arm64-v8a-release.apk"
RELEASE = "release.json"


def current(release_dir: Path) -> dict[str, Any] | None:
    path = release_dir / RELEASE
    if not path.is_file():
        return None
    data: dict[str, Any] = json.loads(path.read_text())
    return data if (release_dir / data["file"]).is_file() else None


def publish(
    source: Path, release_dir: Path, notes: str = "", minimum_build: int = 0
) -> dict[str, Any]:
    """Publie l'APK d'une archive GitHub Actions (``footprono-apk.zip``)."""
    if not zipfile.is_zipfile(source):
        raise AppError(f"{source} n'est pas l'archive footprono-apk.zip de GitHub Actions")
    with zipfile.ZipFile(source) as archive:
        names = set(archive.namelist())
        if RELEASE not in names or APK_IN_ZIP not in names:
            raise AppError(
                f"archive incomplète : {RELEASE} et {APK_IN_ZIP} attendus "
                "(construction antérieure au numéro de version ?)"
            )
        build = int(json.loads(archive.read(RELEASE))["build"])
        previous = current(release_dir)
        if previous is not None and build <= int(previous["build"]):
            raise AppError(
                f"construction {build} déjà publiée ou plus ancienne que {previous['build']}"
            )
        release_dir.mkdir(parents=True, exist_ok=True)
        name = f"footprono-{build}.apk"
        with archive.open(APK_IN_ZIP) as src, (release_dir / name).open("wb") as dst:
            shutil.copyfileobj(src, dst)
    content = (release_dir / name).read_bytes()
    info = {
        "build": build,
        "file": name,
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "notes": notes.strip(),
        "minimum_build": minimum_build,
        "published_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (release_dir / RELEASE).write_text(json.dumps(info, ensure_ascii=False, indent=2))
    # Garde l'avant-dernière version (retour arrière), supprime les plus anciennes.
    apks = sorted(release_dir.glob("footprono-*.apk"), key=lambda p: p.stat().st_mtime)
    for old in apks[:-2]:
        old.unlink()
    return info
