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


def test_raw_files_compressed_and_read_back(tmp_path: Path) -> None:
    from footprono.ingestion import raw_store

    folder = tmp_path / "api_football" / "odds"
    folder.mkdir(parents=True)
    old = folder / "20261120.abc.json"
    old.write_bytes(b'{"cotes": "' + b"x" * 5000 + b'"}')
    count, before, after = raw_store.compress_existing(tmp_path, DataSource.API_FOOTBALL)
    assert (count, before) == (1, 5013)
    assert after < before / 10
    assert not old.exists()
    # Le chemin enregistré avant la compression se lit toujours.
    assert raw_store.read(old) == b'{"cotes": "' + b"x" * 5000 + b'"}'
    assert raw_store.compress_existing(tmp_path, DataSource.API_FOOTBALL)[0] == 0


async def test_new_api_football_files_written_compressed(
    db_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    from footprono.ingestion import raw_store

    async with db_factory() as session:
        raw_id = await raw_store.archive(
            session, tmp_path, DataSource.API_FOOTBALL, "https://x/odds", "odds/a.json", b"{}" * 900
        )
        row = await session.get(RawFile, raw_id)
    assert row is not None
    assert row.path.endswith(".json.gz")
    assert row.size_bytes == 1800  # taille du contenu d'origine
    assert raw_store.read(row.path) == b"{}" * 900
