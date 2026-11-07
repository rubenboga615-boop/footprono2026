"""Logos des équipes : numéro API-Football appris à l'import, image gardée par le serveur."""

import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.football import logos
from footprono.football.models import DataSource, TeamAlias
from footprono.ingestion.service import IngestionRequest

from .conftest import make_settings
from .test_ingestion import _af_item, ingest

Factory = async_sessionmaker[AsyncSession]
PNG = b"\x89PNG\r\n\x1a\nlogo"


async def test_logos_learned_on_import_and_served(
    db_factory: Factory,
    client: AsyncClient,
    app: FastAPI,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app.state.settings = make_settings(raw_data_dir=tmp_path / "raw")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/565.png"):
            return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
        return httpx.Response(404, text="introuvable")

    monkeypatch.setattr(logos, "transport", httpx.MockTransport(handler))
    folder = tmp_path / "archive" / "SWZ"
    (folder / "2024").mkdir(parents=True)
    (folder / "league.json").write_text(json.dumps([{"league": {"id": 207}}]))
    yb, basel = (565, "BSC Young Boys"), (551, "FC Basel 1893")
    (folder / "2024" / "fixtures.json").write_text(
        json.dumps([_af_item(1, "2024-08-10", yb, basel, (2, 1))])
    )
    request = IngestionRequest(DataSource.API_FOOTBALL, ["SUI"], [2024], tmp_path / "archive")
    await ingest(db_factory, tmp_path, request)
    async with db_factory() as session:
        # Noms API-Football → équipes du référentiel (surnoms de la source).
        teams = dict(
            (
                await session.execute(
                    select(TeamAlias.alias, TeamAlias.team_id).where(
                        TeamAlias.alias.in_(["BSC Young Boys", "FC Basel 1893"])
                    )
                )
            )
            .tuples()
            .all()
        )
        assert await logos.api_id(session, teams["BSC Young Boys"]) == 565

    r = await client.get(f"/api/v1/teams/{teams['BSC Young Boys']}/logo")
    assert (r.status_code, r.content, r.headers["content-type"]) == (200, PNG, "image/png")
    assert "max-age=604800" in r.headers["cache-control"]
    again = await client.get(f"/api/v1/teams/{teams['BSC Young Boys']}/logo")
    assert again.status_code == 200
    assert calls.count("/football/teams/565.png") == 1  # téléchargé une seule fois

    # Pas d'image chez API-Football : 404 (initiales dans l'application), pas redemandée.
    assert (await client.get(f"/api/v1/teams/{teams['FC Basel 1893']}/logo")).status_code == 404
    assert (await client.get(f"/api/v1/teams/{teams['FC Basel 1893']}/logo")).status_code == 404
    assert calls.count("/football/teams/551.png") == 1
    assert (await client.get("/api/v1/teams/999999/logo")).status_code == 404
