"""Prédictions enregistrées et API, sur une saison réelle dont la fin est « à venir »."""

from datetime import date
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.engine import ENGINE_VERSION
from footprono.football.models import DataSource, Match, MatchStatus
from footprono.ingestion.service import IngestionRequest, run_ingestion
from footprono.predictions.models import MatchPrediction
from footprono.predictions.service import predict_upcoming

from .conftest import make_settings

FIXTURES = Path(__file__).parent / "fixtures"
AS_OF = date(2025, 5, 18)  # les deux dernières journées de 2024-25 deviennent « à venir »


@pytest.fixture
async def upcoming(db_factory: async_sessionmaker[AsyncSession], tmp_path: Path) -> list[int]:
    await run_ingestion(
        db_factory,
        make_settings(raw_data_dir=tmp_path),
        [
            IngestionRequest(DataSource.FOOTBALL_DATA, ["EPL"], [2024], FIXTURES / "football-data"),
            IngestionRequest(DataSource.UNDERSTAT, ["EPL"], [2024], FIXTURES / "understat"),
        ],
    )
    async with db_factory() as session:
        await session.execute(
            update(Match)
            .where(Match.match_date >= AS_OF)
            .values(
                status=MatchStatus.SCHEDULED,
                home_goals=None,
                away_goals=None,
                home_goals_ht=None,
                away_goals_ht=None,
            )
        )
        await session.commit()
        return list(await session.scalars(select(Match.id).where(Match.match_date >= AS_OF)))


async def test_predict_upcoming_stores_coherent_predictions(
    db_factory: async_sessionmaker[AsyncSession], upcoming: list[int]
) -> None:
    assert len(upcoming) >= 10
    async with db_factory() as session:
        run = await predict_upcoming(session, AS_OF, days_ahead=30)
        assert run.status == "ok"
        assert run.engine_version == ENGINE_VERSION
        assert run.report["competitions"]["EPL"]["matches"] == len(upcoming)
        preds = (await session.scalars(select(MatchPrediction))).all()
    assert sorted(p.match_id for p in preds) == sorted(upcoming)
    for p in preds:
        one_x_two = sum(p.markets[f"1X2||{s}"][0] for s in ("home", "draw", "away"))
        assert one_x_two == pytest.approx(1.0, abs=1e-5)
        over = p.markets["OU|2.5|over"][0] + p.markets["OU|2.5|under"][0]
        assert over == pytest.approx(1.0, abs=1e-5)
        assert 0.2 < p.lambda_home < 4
        assert 0.2 < p.lambda_away < 4
        assert "CORNERS_OU|9.5|over" in p.markets
        assert "BOOKING_POINTS_OU|45.5|over" in p.markets
        assert p.counts["corners"]["mean_home"] > 0
        assert p.context["points"][0] >= 0


async def test_prediction_api(
    db_factory: async_sessionmaker[AsyncSession], upcoming: list[int], client: AsyncClient
) -> None:
    missing = await client.get(f"/api/v1/matches/{upcoming[0]}/prediction")
    assert missing.status_code == 404

    async with db_factory() as session:
        await predict_upcoming(session, AS_OF, days_ahead=30)

    detail = await client.get(f"/api/v1/matches/{upcoming[0]}/prediction")
    assert detail.status_code == 200
    body = detail.json()
    assert body["engine_version"] == ENGINE_VERSION
    one_x_two = [m for m in body["markets"] if m["market"] == "1X2"]
    assert len(one_x_two) == 3
    for m in one_x_two:
        assert m["fair_odds"] == pytest.approx(1 / m["probability"], rel=1e-3)
    ah = await client.get(f"/api/v1/matches/{upcoming[0]}/prediction", params={"market": "ah"})
    assert {m["market"] for m in ah.json()["markets"]} == {"AH"}

    listing = await client.get(
        "/api/v1/predictions/upcoming", params={"date_from": "2025-05-18", "date_to": "2025-06-30"}
    )
    assert listing.status_code == 200
    items = listing.json()
    assert len(items) == len(upcoming)
    assert all(item["prediction"] is not None for item in items)
    first = items[0]["prediction"]
    total = (
        first["home"]["probability"] + first["draw"]["probability"] + first["away"]["probability"]
    )
    assert total == pytest.approx(1.0, abs=1e-5)

    runs = await client.get("/api/v1/predictions/runs")
    assert runs.status_code == 200
    assert runs.json()[0]["status"] == "ok"
