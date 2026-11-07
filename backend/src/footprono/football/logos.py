"""Logos des équipes : numéro API-Football de chaque équipe, image servie par FootProba.

Le numéro est gardé comme pour les coupes (surnom « #numéro » de la source API-Football),
appris à chaque import et à chaque passage du direct. L'image vient de la bibliothèque
d'images d'API-Football (aucune requête comptée), téléchargée une fois puis gardée sur le
disque du serveur : l'application la lit chez FootProba (version web : même adresse, pas
de blocage du navigateur).
"""

import asyncio
import logging
from collections.abc import Iterable
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.football.models import DataSource, TeamAlias

logger = logging.getLogger(__name__)
LOGO_URL = "https://media.api-sports.io/football/teams/{}.png"
# Remplacé par les tests ; None : vrai réseau.
transport: httpx.AsyncBaseTransport | None = None


async def remember_api_ids(session: AsyncSession, pairs: Iterable[tuple[int, int | None]]) -> None:
    """(équipe en base, numéro API-Football) : surnom « #numéro » ajouté s'il manque."""
    seen = {(team, api) for team, api in pairs if api}
    for team_id, api_id in seen:
        await session.execute(
            insert(TeamAlias)
            .values(team_id=team_id, source=DataSource.API_FOOTBALL, alias=f"#{api_id}")
            .on_conflict_do_nothing(index_elements=["source", "alias"])
        )


async def api_id(session: AsyncSession, team_id: int) -> int | None:
    alias = await session.scalar(
        select(TeamAlias.alias)
        .where(
            TeamAlias.team_id == team_id,
            TeamAlias.source == DataSource.API_FOOTBALL,
            TeamAlias.alias.startswith("#"),
        )
        .order_by(TeamAlias.id)
        .limit(1)
    )
    return int(alias[1:]) if alias and alias[1:].isdigit() else None


async def logo_file(folder: Path, number: int) -> Path | None:
    """Image du logo, téléchargée la première fois ; None si elle n'existe pas."""
    path = folder / f"{number}.png"
    if path.exists():
        return path if path.stat().st_size > 0 else None
    try:
        async with httpx.AsyncClient(timeout=10, transport=transport) as client:
            r = await client.get(LOGO_URL.format(number))
    except httpx.HTTPError:
        logger.warning("team_logo_unreachable", extra={"api_id": number})
        return None
    ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("image/")
    # Pas d'image : un fichier vide évite de la redemander à chaque affichage.
    await asyncio.to_thread(_save, path, r.content if ok else b"")
    return path if ok else None


def _save(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
