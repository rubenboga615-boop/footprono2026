"""Espace disque (console, lecture seule)."""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.console import disk
from footprono.football.models import DataSource, RawFile

from .conftest import make_settings


async def test_disk_report_sizes_and_growth(
    db_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    raw = tmp_path / "raw"
    (raw / "api_football" / "odds").mkdir(parents=True)
    (raw / "api_football" / "odds" / "a.json").write_bytes(b"x" * 3000)
    (raw / "football_data").mkdir()
    (raw / "football_data" / "E0.csv").write_bytes(b"y" * 1000)
    settings = make_settings(raw_data_dir=raw, console_files_dir=tmp_path / "files")
    now = datetime.now(UTC)
    async with db_factory() as session:
        session.add_all(
            [
                RawFile(
                    source=DataSource.API_FOOTBALL, origin="https://x/odds", path="a",
                    sha256="1" * 64, size_bytes=3000, fetched_at=now,
                ),
                RawFile(
                    source=DataSource.API_FOOTBALL, origin="https://x/fixtures?ids=", path="b",
                    sha256="2" * 64, size_bytes=500, fetched_at=now,
                ),
            ]
        )  # fmt: skip
        await session.commit()
        report = await disk.disk_report(session, settings, now)
    assert report["folders"]["fichiers bruts des sources"] == (4000, 2)
    assert report["raw_children"][0] == ("api_football", 3000, 1)
    assert dict(report["raw_growth_7d"])["cotes"] == [1, 3000]
    assert dict(report["raw_growth_7d"])["direct et matchs complétés"] == [1, 500]
    assert report["database"] > 0
    lines = disk.format_report(report)
    assert any(line.startswith("Base de données") for line in lines)
    assert any("cotes" in line for line in lines)
