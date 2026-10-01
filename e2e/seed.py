"""Base de bout en bout : vraie saison 2024-25 (jeux d'essai du dépôt) dont les
derniers matchs redeviennent « à venir » (décalés à partir de demain), prédits
par le moteur, avec des cotes 1xBet d'essai dérivées des probabilités (marge 6 %).

Base dédiée : jamais lancé sur la base de production.
    FP_DATABASE_URL=…/footprono_e2e python e2e/seed.py
"""

import asyncio
import os
import tempfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select, text

from footprono.core.config import get_settings
from footprono.db.session import create_engine, create_session_factory
from footprono.football.models import BookmakerOdds, DataSource, Match
from footprono.ingestion.service import IngestionRequest, run_ingestion
from footprono.predictions.models import MatchPrediction
from footprono.predictions.service import predict_upcoming

FIXTURES = Path(__file__).resolve().parents[1] / "backend" / "tests" / "fixtures"
CUT = date(2025, 5, 18)  # les deux dernières journées de 2024-25
BETS = {
    "Match Winner": [
        ("Home", "1X2||home"),
        ("Draw", "1X2||draw"),
        ("Away", "1X2||away"),
    ],
    "Goals Over/Under": [("Over 2.5", "OU|2.5|over"), ("Under 2.5", "OU|2.5|under")],
    "Both Teams Score": [("Yes", "BTTS||yes"), ("No", "BTTS||no")],
}


async def main() -> None:
    assert "e2e" in os.environ.get("FP_DATABASE_URL", ""), "base de bout en bout uniquement"
    # Copies des fichiers bruts dans un dossier temporaire (jamais dans le dépôt).
    os.environ.setdefault("FP_RAW_DATA_DIR", tempfile.mkdtemp(prefix="footprono-e2e-"))
    get_settings.cache_clear()
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    await run_ingestion(
        factory,
        settings,
        [
            IngestionRequest(DataSource.FOOTBALL_DATA, ["EPL"], [2024], FIXTURES / "football-data"),
            IngestionRequest(DataSource.UNDERSTAT, ["EPL"], [2024], FIXTURES / "understat"),
        ],
    )
    today = datetime.now(UTC).date()
    shift = (today + timedelta(days=1) - CUT).days
    async with factory() as session:
        await session.execute(
            text(
                "UPDATE matches SET status = 'scheduled', home_goals = NULL, away_goals = NULL, "
                "home_goals_ht = NULL, away_goals_ht = NULL, api_status = 'NS', "
                "match_date = match_date + CAST(:shift AS integer), kickoff_at = "
                "(match_date + CAST(:shift AS integer))::timestamp + interval '19 hours' "
                "WHERE match_date >= :cut"
            ),
            {"shift": shift, "cut": CUT},
        )
        await session.commit()
    async with factory() as session:
        run = await predict_upcoming(session, today, 30)
        print("prédiction :", run.status, run.report.get("competitions"))
    async with factory() as session:
        now = datetime.now(UTC)
        for p in (await session.scalars(select(MatchPrediction))).all():
            for bet, values in BETS.items():
                for value, key in values:
                    price = max(1.02, round(1 / (p.markets[key][0] * 1.06), 2))
                    session.add(
                        BookmakerOdds(
                            match_id=p.match_id,
                            fetched_at=now,
                            last_seen_at=now,
                            bookmaker="1xBet",
                            bet=bet,
                            value=value,
                            price=Decimal(str(price)),
                        )
                    )
        await session.commit()
        upcoming = await session.scalar(
            select(text("count(*)")).select_from(Match).where(Match.status == "scheduled")
        )
        print("matchs à venir :", upcoming)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
