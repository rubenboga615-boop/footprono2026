"""Archivage des fichiers bruts et téléchargement depuis les sources.

Chaque fichier ingéré est conservé tel quel sous ``FP_RAW_DATA_DIR``, nommé par
son empreinte SHA-256, et enregistré dans ``raw_files`` : toute donnée en base
peut être rattachée au fichier exact dont elle provient.
"""

import asyncio
import hashlib
import logging
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.football.models import DataSource, RawFile

logger = logging.getLogger(__name__)

USER_AGENT = "FootProno/0.1 (+https://github.com/rubenboga615-boop/footprono2026)"


class SourceUnavailableError(Exception):
    """La source n'a pas pu fournir le fichier (réseau, erreur HTTP, fichier absent)."""


async def archive(
    session: AsyncSession,
    raw_dir: Path,
    source: DataSource,
    origin: str,
    relative_name: str,
    content: bytes,
) -> int:
    """Écrit le fichier (si nouveau) et renvoie l'identifiant de sa ligne ``raw_files``."""
    digest = hashlib.sha256(content).hexdigest()
    stem, dot, suffix = relative_name.rpartition(".")
    name = f"{stem}.{digest[:12]}{dot}{suffix}" if dot else f"{relative_name}.{digest[:12]}"
    path = raw_dir / source.value / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(content)
        tmp.replace(path)

    await session.execute(
        insert(RawFile)
        .values(
            source=source,
            origin=origin,
            path=str(path),
            sha256=digest,
            size_bytes=len(content),
        )
        .on_conflict_do_nothing(index_elements=["source", "sha256"])
    )
    raw_id = await session.scalar(
        select(RawFile.id).where(RawFile.source == source, RawFile.sha256 == digest)
    )
    assert raw_id is not None
    return raw_id


async def download(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    attempts: int = 4,
    request_timeout: float = 30.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes:
    """Télécharge ``url`` avec relances. 404 → ``SourceUnavailableError`` immédiate."""
    last_error: str = ""
    async with httpx.AsyncClient(
        timeout=request_timeout,
        transport=transport,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, **(headers or {})},
    ) as client:
        for attempt in range(1, attempts + 1):
            try:
                response = await client.get(url)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if response.status_code == 200:
                    return response.content
                if response.status_code == 404:
                    raise SourceUnavailableError(f"{url} : introuvable (404)")
                last_error = f"HTTP {response.status_code}"
            logger.warning(
                "download_retry", extra={"url": url, "attempt": attempt, "error": last_error}
            )
            if attempt < attempts:
                await asyncio.sleep(2**attempt)
    raise SourceUnavailableError(f"{url} : échec après {attempts} tentatives ({last_error})")
