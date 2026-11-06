"""Couverture des données : ce qui manque et la commande qui le comble."""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.football.models import DataSource
from footprono.ingestion import cups
from footprono.ingestion.coverage import coverage_report, format_coverage
from footprono.ingestion.service import IngestionRequest, run_ingestion

from .conftest import make_settings

FIXTURES = Path(__file__).parent / "fixtures"


async def test_coverage_lists_missing_sources(
    db_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    await run_ingestion(
        db_factory,
        make_settings(raw_data_dir=tmp_path),
        [IngestionRequest(DataSource.FOOTBALL_DATA, ["EPL"], [2024], FIXTURES / "football-data")],
    )
    async with db_factory() as session:
        # Un match de coupe d'Europe en base : hors du rapport (il faisait planter le calcul).
        await cups.sync_cups(session)
        await cups.load_cup_fixtures(session, "UCL", [{
            "fixture": {"id": 7000, "date": "2024-09-17T19:00:00+00:00",
                        "status": {"short": "FT"}},
            "league": {"id": 2, "season": 2024, "round": "League Stage - 1"},
            "teams": {"home": {"id": 100, "name": "Club 100"},
                      "away": {"id": 101, "name": "Club 101"}},
            "score": {"fulltime": {"home": 1, "away": 0}, "halftime": {"home": 0, "away": 0}},
        }])  # fmt: skip
        await session.commit()
        report = await coverage_report(session)
    (row,) = report["rows"]
    assert (row["competition"], row["season"], row["matches"]) == ("EPL", 2024, 380)
    assert row["ht"] == row["fd_stats"] == row["referee"] == 1.0  # football-data
    assert row["ah_odds"] > 0.9  # handicap asiatique (football-data)
    assert row["xg"] == row["api_full"] == 0.0  # Understat et API-Football pas encore collectés
    text = format_coverage(report)
    assert "ingest.sh api-football --seasons 2024 --competitions EPL" in text
    assert "ingest.sh understat --seasons 2024 --competitions EPL" in text
