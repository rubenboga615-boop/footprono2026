"""Version web de l'application (iPhone et ordinateur), publiée par le serveur.

Publier : console → Versions → « Version web », ou sur le serveur
``footprono-admin publish-web footprono-web.zip``, avec l'archive téléchargée
depuis GitHub Actions (dossier ``build/web`` de Flutter, construit avec
``--base-href /app/``).

Chaque publication est extraite dans son propre dossier, puis le lien
``current`` bascule d'un coup vers elle : un joueur ne voit jamais un mélange de
deux versions. L'avant-dernière est gardée (retour arrière).
"""

import json
import os
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from footprono.core.errors import AppError

CURRENT = "current"
RELEASE = "release.json"
MAX_FILES = 2000
MAX_UNPACKED = 300 * 1024 * 1024


def served_dir(release_dir: Path) -> Path:
    return release_dir / CURRENT


def current(release_dir: Path) -> dict[str, Any] | None:
    folder = served_dir(release_dir)
    if not (folder / "index.html").is_file():
        return None
    info: dict[str, Any] = {"published_at": None, "build": None}
    if (folder / RELEASE).is_file():
        info.update(json.loads((folder / RELEASE).read_text()))
    return info


def _safe_names(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = [m for m in archive.infolist() if not m.is_dir()]
    if len(members) > MAX_FILES:
        raise AppError(f"archive web : trop de fichiers ({len(members)})")
    if sum(m.file_size for m in members) > MAX_UNPACKED:
        raise AppError("archive web trop volumineuse une fois décompressée")
    for member in members:
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts or "\\" in member.filename:
            raise AppError(f"archive web : chemin refusé {member.filename!r}")
    return members


def publish(source: Path, release_dir: Path) -> dict[str, Any]:
    """Publie l'archive ``footprono-web.zip`` de GitHub Actions."""
    if not zipfile.is_zipfile(source):
        raise AppError(f"{source.name} n'est pas l'archive footprono-web.zip de GitHub Actions")
    with zipfile.ZipFile(source) as archive:
        members = _safe_names(archive)
        names = {m.filename for m in members}
        if "index.html" not in names or "flutter_bootstrap.js" not in names:
            raise AppError(
                "archive incomplète : index.html et flutter_bootstrap.js attendus "
                "(archive footprono-web, pas footprono-apk ?)"
            )
        if b'<base href="/app/">' not in archive.read("index.html"):
            raise AppError("version web construite sans --base-href /app/")
        stamp = datetime.now(UTC)
        folder = release_dir / f"web-{stamp:%Y%m%d-%H%M%S-%f}"
        folder.mkdir(parents=True)
        for member in members:
            target = folder / member.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    info: dict[str, Any] = {}
    if (folder / RELEASE).is_file():
        info.update(json.loads((folder / RELEASE).read_text()))
    info["published_at"] = stamp.isoformat(timespec="seconds")
    (folder / RELEASE).write_text(json.dumps(info, ensure_ascii=False, indent=2))
    # Bascule d'un coup : nouveau lien, puis remplacement atomique de « current ».
    link = release_dir / f".{CURRENT}-{folder.name}"
    link.symlink_to(folder.name)
    os.replace(link, served_dir(release_dir))
    versions = sorted(p for p in release_dir.glob("web-*") if p.is_dir())
    for old in versions[:-2]:
        shutil.rmtree(old, ignore_errors=True)
    return info
