"""API de lecture des données sportives, sur une saison réelle ingérée."""

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.football.models import DataSource
from footprono.ingestion.service import IngestionRequest, run_ingestion

from .conftest import make_settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
async def epl_2024(db_factory: async_sessionmaker[AsyncSession], tmp_path: Path) -> None:
    await run_ingestion(
        db_factory,
        make_settings(raw_data_dir=tmp_path),
        [
            IngestionRequest(DataSource.FOOTBALL_DATA, ["EPL"], [2024], FIXTURES / "football-data"),
            IngestionRequest(DataSource.UNDERSTAT, ["EPL"], [2024], FIXTURES / "understat"),
        ],
    )


pytestmark = pytest.mark.usefixtures("epl_2024")


async def test_competitions(client: AsyncClient) -> None:
    response = await client.get("/api/v1/competitions")
    assert response.status_code == 200
    competitions = {c["code"]: c for c in response.json()}
    assert set(competitions) == {
        "EPL", "LA_LIGA", "SERIE_A", "BUNDESLIGA", "LIGUE_1", "POR", "BEL", "NED", "GRE", "TUR",
        "SCO", "SUI", "NOR", "SWE", "DEN", "AUT", "POL", "CZE", "CRO", "ROU",
    }  # fmt: skip
    assert competitions["EPL"]["seasons"] == [
        {"start_year": 2024, "label": "2024-25", "matches": 380, "finished": 380}
    ]
    assert competitions["LIGUE_1"]["seasons"] == []


async def test_season_teams(client: AsyncClient) -> None:
    response = await client.get("/api/v1/competitions/epl/seasons/2024/teams")
    assert response.status_code == 200
    names = [t["name"] for t in response.json()]
    assert len(names) == 20
    assert "Manchester United" in names

    missing = await client.get("/api/v1/competitions/EPL/seasons/1999/teams")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


async def test_list_matches_with_filters_and_pagination(client: AsyncClient) -> None:
    page = (await client.get("/api/v1/matches", params={"competition": "EPL", "limit": 10})).json()
    assert (page["total"], len(page["items"]), page["offset"]) == (380, 10, 0)
    first = page["items"][0]
    assert (first["home_team"]["name"], first["away_team"]["name"]) == (
        "Manchester United",
        "Fulham",
    )
    assert (first["match_date"], first["home_goals"], first["away_goals"]) == ("2024-08-16", 1, 0)

    second_page = (await client.get("/api/v1/matches", params={"limit": 10, "offset": 10})).json()
    assert {m["id"] for m in second_page["items"]}.isdisjoint(m["id"] for m in page["items"])

    team_id = first["home_team"]["id"]
    by_team = (await client.get("/api/v1/matches", params={"team_id": team_id})).json()
    assert by_team["total"] == 38

    window = (
        await client.get(
            "/api/v1/matches", params={"date_from": "2024-08-16", "date_to": "2024-08-18"}
        )
    ).json()
    assert window["total"] == 9  # le 10e match de la journée a lieu le lundi 19

    scheduled = (await client.get("/api/v1/matches", params={"status": "scheduled"})).json()
    assert scheduled["total"] == 0


async def test_list_matches_validates_parameters(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/matches", params={"limit": 1000})).status_code == 422
    assert (await client.get("/api/v1/matches", params={"status": "live"})).status_code == 422


async def test_match_detail(client: AsyncClient) -> None:
    first = (await client.get("/api/v1/matches", params={"limit": 1})).json()["items"][0]
    detail = (await client.get(f"/api/v1/matches/{first['id']}")).json()

    assert detail["stats"]["home_shots"] == 14
    assert detail["stats"]["referee"] == "R Jones"
    # Statistiques API-Football non chargées dans ce test : liste vide, jamais inventée.
    assert (detail["api_football_id"], detail["team_stats"]) == (None, [])
    assert len(detail["advanced_stats"]) == 2
    home_xg = next(a for a in detail["advanced_stats"] if a["team_id"] == first["home_team"]["id"])
    assert home_xg["xg"] == "2.0427"
    b365_home = [
        o
        for o in detail["odds"]
        if (o["bookmaker"], o["market"], o["timing"], o["selection"])
        == ("B365", "1X2", "pre", "home")
    ]
    assert [o["price"] for o in b365_home] == ["1.600"]


async def test_match_not_found(client: AsyncClient) -> None:
    response = await client.get("/api/v1/matches/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_ingestion_runs_and_quality(client: AsyncClient) -> None:
    runs = (await client.get("/api/v1/ingestion/runs")).json()
    assert [r["status"] for r in runs] == ["ok"]
    detail = (await client.get(f"/api/v1/ingestion/runs/{runs[0]['id']}")).json()
    assert [f["status"] for f in detail["report"]["files"]] == ["ok", "ok"]
    assert (await client.get("/api/v1/ingestion/runs/999")).status_code == 404

    quality = (await client.get("/api/v1/data/quality")).json()
    assert quality["errors"] == 0
