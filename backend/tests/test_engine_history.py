"""Chargement de l'historique du moteur depuis la base (fichiers réels)."""

from pathlib import Path

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.engine.history import load_history
from footprono.football.models import DataSource
from footprono.ingestion.service import IngestionRequest, run_ingestion

from .conftest import make_settings

FIXTURES = Path(__file__).parent / "fixtures"


async def test_load_history_from_real_season(
    db_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    await run_ingestion(
        db_factory,
        make_settings(raw_data_dir=tmp_path),
        [
            IngestionRequest(DataSource.FOOTBALL_DATA, ["EPL"], [2024], FIXTURES / "football-data"),
            IngestionRequest(DataSource.UNDERSTAT, ["EPL"], [2024], FIXTURES / "understat"),
        ],
    )
    async with db_factory() as session:
        hist = await load_history(session)

    assert len(hist) == 380
    assert hist.finished.all()
    assert not hist.excluded.any()
    assert not np.isnan(hist.hxg).any()
    assert (np.diff(hist.date.astype("int64")) >= 0).all()  # ordre chronologique
    first = int(np.argmin(hist.match_id))
    assert (hist.hg[first], hist.ag[first], hist.hht[first]) == (1, 0, 0)
    # Cotes de référence : un seul bookmaker par marché (Pinnacle en priorité).
    close = hist.odds["close_1x2"]
    assert not np.isnan(close).any()
    margin = (1 / close).sum(axis=1)
    assert ((margin > 1.0) & (margin < 1.1)).all()
    assert not np.isnan(hist.odds["pre_ou25"]).any()
