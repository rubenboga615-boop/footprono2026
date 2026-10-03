"""Ingestion de bout en bout sur un vrai PostgreSQL, à partir de fichiers réels."""

import shutil
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.football.models import (
    DataSource,
    IngestionRun,
    Match,
    MatchAdvancedStats,
    MatchOdds,
    MatchStatus,
    RawFile,
)
from footprono.ingestion import loader, raw_store, service
from footprono.ingestion.quality import run_quality_checks
from footprono.ingestion.service import IngestionRequest, run_ingestion
from footprono.ingestion.sources.common import ParseIssues
from footprono.ingestion.sources.understat import UnderstatMatch, UnderstatSeason

from .conftest import make_settings

FIXTURES = Path(__file__).parent / "fixtures"
FD_DIR = FIXTURES / "football-data"
US_DIR = FIXTURES / "understat"

Factory = async_sessionmaker[AsyncSession]


def fd(competition: str, season: int, from_dir: Path = FD_DIR) -> IngestionRequest:
    return IngestionRequest(DataSource.FOOTBALL_DATA, [competition], [season], from_dir)


def us(competition: str, season: int, from_dir: Path = US_DIR) -> IngestionRequest:
    return IngestionRequest(DataSource.UNDERSTAT, [competition], [season], from_dir)


async def ingest(factory: Factory, tmp_path: Path, *requests: IngestionRequest) -> dict[str, Any]:
    settings = make_settings(raw_data_dir=tmp_path / "raw")
    return await run_ingestion(factory, settings, list(requests))


async def count(factory: Factory, model: type[Any]) -> int:
    async with factory() as session:
        return await session.scalar(select(func.count()).select_from(model)) or 0


def _archived_under(paths: list[str], root: Path) -> bool:
    return all(Path(p).is_file() and Path(p).is_relative_to(root) for p in paths)


async def test_ingests_real_season_from_both_sources(db_factory: Factory, tmp_path: Path) -> None:
    report = await ingest(db_factory, tmp_path, fd("EPL", 2024), us("EPL", 2024))

    assert report["status"] == "ok", report
    fd_file, us_file = report["files"]
    assert fd_file["status"] == us_file["status"] == "ok"
    assert fd_file["matches_inserted"] == 380
    assert us_file["matches_inserted"] == 0  # Understat complète, ne crée pas de doublon
    assert us_file["advanced_stats_upserted"] == 760
    assert await count(db_factory, Match) == 380
    assert await count(db_factory, MatchAdvancedStats) == 760
    assert await count(db_factory, MatchOdds) == fd_file["odds_upserted"] > 0

    season = next(s for s in report["quality"]["seasons"] if s["competition"] == "EPL")
    assert (season["finished"], season["xg_coverage"], season["odds_coverage"]) == (380, 1, 1)
    assert report["quality"]["errors"] == 0

    # Fichiers bruts archivés tels quels et rattachés en base.
    async with db_factory() as session:
        raw_files = (await session.scalars(select(RawFile))).all()
        run = await session.get(IngestionRun, report["run_id"])
    assert len(raw_files) == 3
    assert _archived_under([r.path for r in raw_files], tmp_path / "raw")
    assert run is not None
    assert run.status == "ok"
    assert run.finished_at is not None


async def test_ingestion_is_idempotent(db_factory: Factory, tmp_path: Path) -> None:
    await ingest(db_factory, tmp_path, fd("EPL", 2024), us("EPL", 2024))
    before = [await count(db_factory, m) for m in (Match, MatchOdds, MatchAdvancedStats, RawFile)]

    report = await ingest(db_factory, tmp_path, fd("EPL", 2024), us("EPL", 2024))

    after = [await count(db_factory, m) for m in (Match, MatchOdds, MatchAdvancedStats, RawFile)]
    assert after == before
    assert all(f["matches_inserted"] == 0 for f in report["files"])
    assert report["files"][1]["matches_updated"] == 0


async def test_unknown_team_rejects_whole_file(db_factory: Factory, tmp_path: Path) -> None:
    source = FD_DIR / "2425" / "E0.csv"
    tampered_dir = tmp_path / "fd"
    (tampered_dir / "2425").mkdir(parents=True)
    content = source.read_bytes().replace(b",Man United,", b",Unknown FC,", 1)
    (tampered_dir / "2425" / "E0.csv").write_bytes(content)

    report = await ingest(db_factory, tmp_path, fd("EPL", 2024, tampered_dir))

    assert report["status"] == "failed"
    assert report["files"][0]["status"] == "rejected"
    assert "Unknown FC" in report["files"][0]["error"]
    assert await count(db_factory, Match) == 0


async def test_missing_file_is_reported_never_hidden(db_factory: Factory, tmp_path: Path) -> None:
    report = await ingest(db_factory, tmp_path, fd("EPL", 2023))

    assert report["status"] == "partial"
    assert report["files"][0]["status"] == "unavailable"
    assert "absent" in report["files"][0]["error"]


async def _rennes_matches_on(factory: Factory, day: str) -> list[Match]:
    async with factory() as session:
        rows = await session.scalars(
            select(Match).where(
                Match.match_date == datetime.fromisoformat(day).date(),
                text(
                    "(home_team_id = (SELECT id FROM teams WHERE name = 'Rennes') "
                    "OR away_team_id = (SELECT id FROM teams WHERE name = 'Rennes'))"
                ),
            )
        )
        return list(rows.all())


def _issues(report: dict[str, Any]) -> list[str]:
    return [i for f in report["files"] for i in f.get("issues", [])]


async def test_source_conflict_understat_after_football_data(
    db_factory: Factory, tmp_path: Path
) -> None:
    # Fichiers réels : football-data publie « Rennes 2-2 PSG » le 23/08/2026,
    # Understat « PSG 0-0 Rennes » le même jour.
    report = await ingest(db_factory, tmp_path, fd("LIGUE_1", 2026), us("LIGUE_1", 2026))

    conflicts = [i for i in _issues(report) if "conflit entre sources" in i]
    assert len(conflicts) == 1
    assert "Paris Saint Germain-Rennes" in conflicts[0]
    matches = await _rennes_matches_on(db_factory, "2026-08-23")
    assert [(m.home_goals, m.away_goals) for m in matches] == [(2, 2)]
    assert not [f for f in report["quality"]["findings"] if f["check"] == "doublons"]


async def test_source_conflict_football_data_after_understat(
    db_factory: Factory, tmp_path: Path
) -> None:
    await ingest(db_factory, tmp_path, us("LIGUE_1", 2026))
    assert len(await _rennes_matches_on(db_factory, "2026-08-23")) == 1

    report = await ingest(db_factory, tmp_path, fd("LIGUE_1", 2026))

    assert any("supprimé" in i for i in _issues(report))
    matches = await _rennes_matches_on(db_factory, "2026-08-23")
    assert [(m.home_goals, m.away_goals) for m in matches] == [(2, 2)]
    assert matches[0].football_data_file_id is not None
    assert not [f for f in report["quality"]["findings"] if f["check"] == "doublons"]


async def test_quality_detects_duplicate_fixtures(db_factory: Factory, tmp_path: Path) -> None:
    await ingest(db_factory, tmp_path, fd("LIGUE_1", 2026))
    async with db_factory() as session, session.begin():
        original = (await _rennes_matches_on(db_factory, "2026-08-23"))[0]
        session.add(
            Match(
                season_id=original.season_id,
                home_team_id=original.away_team_id,
                away_team_id=original.home_team_id,
                match_date=original.match_date,
                status=MatchStatus.SCHEDULED,
            )
        )
    async with db_factory() as session:
        quality = await run_quality_checks(session)
    doubles = [f for f in quality["findings"] if f["check"] == "doublons"]
    assert len(doubles) == 2  # une ligne par équipe concernée
    assert all(f["severity"] == "error" for f in doubles)


async def test_quality_detects_tampered_data(db_factory: Factory, tmp_path: Path) -> None:
    await ingest(db_factory, tmp_path, fd("EPL", 2024))
    async with db_factory() as session, session.begin():
        first, second = (await session.scalars(select(Match.id).order_by(Match.id).limit(2))).all()
        await session.execute(update(Match).where(Match.id == first).values(home_goals_ht=9))
        await session.delete(await session.get(Match, second))

    async with db_factory() as session:
        quality = await run_quality_checks(session)

    checks = {f["check"] for f in quality["findings"] if f["severity"] == "error"}
    assert {"scores", "completude"} <= checks
    assert quality["status"] == "error"


def _unplayed(home: str, away: str, kickoff: str) -> UnderstatSeason:
    match = UnderstatMatch(None, datetime.fromisoformat(kickoff), False, home, away, None, None)
    return UnderstatSeason([match], [], ParseIssues())


async def test_unplayed_matches_of_interrupted_season_are_cancelled(db_factory: Factory) -> None:
    async with db_factory() as session, session.begin():
        await loader.sync_reference(session)
        resolver = await loader.TeamResolver.load(session)
        # Ligue 1 2019-20 : arrêtée en mars 2020 → match annulé, pas « à venir ».
        await loader.load_understat(
            session,
            "LIGUE_1",
            2019,
            _unplayed("Rennes", "Lyon", "2020-04-05 15:00:00"),
            0,
            resolver,
        )
        # Saison normale : un match passé jamais joué reste « à venir » et sera signalé.
        await loader.load_understat(
            session,
            "LIGUE_1",
            2018,
            _unplayed("Rennes", "Lyon", "2019-04-05 15:00:00"),
            0,
            resolver,
        )
    async with db_factory() as session:
        statuses = dict(
            (
                await session.execute(
                    text(
                        "SELECT s.start_year, m.status FROM matches m "
                        "JOIN seasons s ON s.id = m.season_id"
                    )
                )
            )
            .tuples()
            .all()
        )
        quality = await run_quality_checks(session)
    assert statuses == {2019: "cancelled", 2018: "scheduled"}
    stale = [f for f in quality["findings"] if f["check"] == "a_venir_depasses"]
    assert [(f["season"], f["severity"]) for f in stale] == [(2018, "error")]
    assert not [f for f in quality["findings"] if f["check"] == "annulations"]


async def test_raw_store_deduplicates_identical_content(
    db_factory: Factory, tmp_path: Path
) -> None:
    copy_dir = tmp_path / "copie"
    shutil.copytree(FD_DIR, copy_dir)
    await ingest(db_factory, tmp_path, fd("EPL", 2024))
    await ingest(db_factory, tmp_path, fd("EPL", 2024, copy_dir))
    assert await count(db_factory, RawFile) == 1


# --- Mode téléchargement (réseau remplacé par une fonction contrôlée) -------


def _fake_download(monkeypatch: pytest.MonkeyPatch, respond: Callable[[str], bytes]) -> list[str]:
    calls: list[str] = []

    async def download(url: str, **_: object) -> bytes:
        calls.append(url)
        return respond(url)

    monkeypatch.setattr(raw_store, "download", download)
    monkeypatch.setattr(service, "DOWNLOAD_PAUSE_SECONDS", 0)
    return calls


async def test_download_mode_ingests_and_reports_progress(
    db_factory: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = (FD_DIR / "2425" / "E0.csv").read_bytes()
    calls = _fake_download(monkeypatch, lambda _url: content)
    messages: list[str] = []

    report = await run_ingestion(
        db_factory,
        make_settings(raw_data_dir=tmp_path),
        [IngestionRequest(DataSource.FOOTBALL_DATA, ["EPL"], [2024])],
        progress=messages.append,
    )

    assert calls == ["https://football-data.co.uk/mmz4281/2425/E0.csv"]
    assert report["status"] == "ok"
    assert report["files"][0]["origin"] == calls[0]
    assert messages[0] == "[1/1] football_data EPL 2024 …"
    assert messages[1].startswith("[1/1] football_data EPL 2024 : ok — matchs +380")


async def test_unreachable_source_is_abandoned_after_consecutive_failures(
    db_factory: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(url: str) -> bytes:
        raise raw_store.SourceUnavailableError(f"{url} : ConnectError")

    calls = _fake_download(monkeypatch, fail)

    report = await run_ingestion(
        db_factory,
        make_settings(raw_data_dir=tmp_path),
        [IngestionRequest(DataSource.FOOTBALL_DATA, ["EPL"], list(range(2016, 2022)))],
    )

    assert len(calls) == service.MAX_CONSECUTIVE_FAILURES
    assert report["status"] == "partial"
    assert [f["status"] for f in report["files"]] == ["unavailable"] * 6
    assert all("non tenté" in f["error"] for f in report["files"][3:])


async def test_missing_files_do_not_abandon_the_source(
    db_factory: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def not_found(url: str) -> bytes:
        raise raw_store.SourceUnavailableError(f"{url} : introuvable (404)", transient=False)

    calls = _fake_download(monkeypatch, not_found)
    await run_ingestion(
        db_factory,
        make_settings(raw_data_dir=tmp_path),
        [IngestionRequest(DataSource.FOOTBALL_DATA, ["EPL"], list(range(2016, 2022)))],
    )
    assert len(calls) == 6


async def test_blocked_understat_page_is_unavailable_and_not_archived(
    db_factory: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_download(monkeypatch, lambda _url: b"<!DOCTYPE html><title>Just a moment...</title>")

    report = await run_ingestion(
        db_factory,
        make_settings(raw_data_dir=tmp_path),
        [IngestionRequest(DataSource.UNDERSTAT, ["EPL"], [2024])],
    )

    assert report["files"][0]["status"] == "unavailable"
    assert "bloqué" in report["files"][0]["error"]
    assert await count(db_factory, RawFile) == 0


async def test_stale_running_run_is_marked_interrupted(db_factory: Factory, tmp_path: Path) -> None:
    async with db_factory() as session, session.begin():
        stale = IngestionRun(source="football_data", status="running", parameters={}, report={})
        stale.started_at = datetime.now(UTC) - timedelta(days=1)
        session.add(stale)
    await ingest(db_factory, tmp_path, fd("EPL", 2023))
    async with db_factory() as session:
        run = await session.get(IngestionRun, stale.id)
    assert run is not None
    assert run.status == "interrupted"
    assert run.finished_at is not None


async def test_belgian_playoffs_regular_season_only(db_factory: Factory, tmp_path: Path) -> None:
    """Phase finale : les affiches rejouées ne sont pas chargées (une affiche par saison),
    sans casser les cotes ; les contrôles d'un simple aller-retour ne s'appliquent pas."""
    report = await ingest(db_factory, tmp_path, fd("BEL", 2024))
    entry = report["files"][0]
    assert entry["status"] == "ok", entry
    assert entry["matches_inserted"] == 240  # 16 équipes, aller-retour
    assert any("phase finale : 72 matchs non chargés" in i for i in entry["issues"])
    async with db_factory() as session:
        quality = await run_quality_checks(session)
    errors = [
        f for f in quality["findings"] if f["competition"] == "BEL" and f["severity"] == "error"
    ]
    assert errors == []


async def test_understat_not_requested_where_it_covers_nothing(
    db_factory: Factory, tmp_path: Path
) -> None:
    report = await ingest(db_factory, tmp_path, us("POR", 2024))
    assert report["files"] == []
