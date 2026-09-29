"""Source API-Football : lecture des fichiers du collecteur, client, chargement.

Les fichiers de ``tests/fixtures/api-football`` sont des copies non modifiées
de fichiers réels produits par le collecteur de l'ancien projet.
"""

import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.football.models import DataSource, Match, MatchTeamStats, StatPeriod
from footprono.ingestion import service
from footprono.ingestion.service import IngestionRequest, run_ingestion
from footprono.ingestion.sources import api_football
from footprono.ingestion.sources.common import ParseIssues

from .conftest import make_settings

FIXTURES = Path(__file__).parent / "fixtures"
API_DIR = FIXTURES / "api-football"

Factory = async_sessionmaker[AsyncSession]


def _read(league: int, season: int) -> Any:
    return json.loads((API_DIR / str(league) / f"{season}.json").read_text())


# --- Lecture (sans base) -------------------------------------------------------


def test_parse_collector_file_real_season() -> None:
    fixtures, issues = api_football.parse_collector_file(_read(39, 2024))

    assert len(fixtures) == 380
    assert issues.items == []
    first = fixtures[0]
    assert (first.home_team, first.away_team, first.home_goals, first.away_goals) == (
        "Manchester United",
        "Fulham",
        1,
        0,
    )
    assert set(first.stats) == set(StatPeriod)
    home, away = first.stats[StatPeriod.FULL]
    assert (home["corners"], away["corners"], home["total_shots"]) == (7, 8, 14)
    assert home["expected_goals"] == Decimal("2.43")
    assert home["possession"] == Decimal(55)
    # Compteur absent = 0 ; fautes jamais fournies par mi-temps = inconnues.
    assert home["red_cards"] == 0
    assert first.stats[StatPeriod.FIRST_HALF][0]["fouls"] is None
    assert first.stats[StatPeriod.FIRST_HALF][0]["corners"] == 2


def test_parse_collector_file_without_statistics() -> None:
    data = {
        "types": None,
        "fixtures": [
            {"id": 1, "d": "2016-08-13", "h": "Hull City", "a": "Leicester", "hg": 2, "ag": 1,
             "ht": 1, "at": 0, "ft": "absent", "h1": None, "h2": None},
        ],
    }  # fmt: skip
    fixtures, _ = api_football.parse_collector_file(data)
    assert fixtures[0].stats == {}


def test_parse_raw_statistics_orders_teams_by_home_id() -> None:
    def block(team_id: int, corners: int) -> dict[str, Any]:
        stats = [
            {"type": "Corner Kicks", "value": corners},
            {"type": "Ball Possession", "value": "61%"},
        ]
        return {"team": {"id": team_id}, "statistics": stats, "statistics_1h": stats}

    issues = ParseIssues()
    # L'équipe extérieure (id 2) arrive en premier : l'ordre est rétabli.
    stats = api_football.parse_statistics([block(2, 3), block(1, 9)], 1, issues)

    assert stats[StatPeriod.FULL][0]["corners"] == 9
    assert stats[StatPeriod.FULL][1]["possession"] == Decimal(61)
    assert StatPeriod.SECOND_HALF not in stats


def test_only_regular_season_finished_matches_are_kept() -> None:
    def item(status: str, round_: str) -> dict[str, Any]:
        return {"fixture": {"status": {"short": status}}, "league": {"round": round_}}

    assert api_football.is_finished_league_match(item("FT", "Regular Season - 3"))
    assert not api_football.is_finished_league_match(item("NS", "Regular Season - 3"))
    assert not api_football.is_finished_league_match(item("FT", "Relegation Round"))


# --- Chargement (vrai PostgreSQL) ----------------------------------------------


async def _count(factory: Factory, *where: Any) -> int:
    async with factory() as session:
        stmt = select(func.count()).select_from(MatchTeamStats).where(*where)
        return await session.scalar(stmt) or 0


async def _ingest(factory: Factory, tmp_path: Path, *requests: IngestionRequest) -> dict[str, Any]:
    return await run_ingestion(
        factory, make_settings(raw_data_dir=tmp_path / "raw"), list(requests)
    )


def _fd(competition: str, season: int) -> IngestionRequest:
    return IngestionRequest(
        DataSource.FOOTBALL_DATA, [competition], [season], FIXTURES / "football-data"
    )


def _api(competition: str, season: int, from_dir: Path = API_DIR) -> IngestionRequest:
    return IngestionRequest(DataSource.API_FOOTBALL, [competition], [season], from_dir)


async def test_collector_import_links_matches_and_loads_periods(
    db_factory: Factory, tmp_path: Path
) -> None:
    report = await _ingest(db_factory, tmp_path, _fd("EPL", 2024), _api("EPL", 2024))

    entry = report["files"][1]
    assert entry["status"] == "ok", entry
    assert entry["issues"] == []
    # 380 matchs x 2 équipes x 3 périodes.
    assert entry["advanced_stats_upserted"] == 2280
    assert await _count(db_factory, MatchTeamStats.period == StatPeriod.FULL) == 760
    async with db_factory() as session:
        linked = await session.scalar(
            select(func.count()).select_from(Match).where(Match.api_football_id.is_not(None))
        )
    assert linked == 380
    season = next(s for s in report["quality"]["seasons"] if s["competition"] == "EPL")
    assert (season["api_stats_coverage"], season["api_halves_coverage"]) == (1, 1)
    assert not [f for f in report["quality"]["findings"] if f["check"] in ("corners", "mi_temps")]

    again = await _ingest(db_factory, tmp_path, _api("EPL", 2024))
    assert await _count(db_factory) == 2280
    assert again["files"][0]["matches_updated"] == 0


async def test_api_football_confirms_football_data_on_rennes_psg(
    db_factory: Factory, tmp_path: Path
) -> None:
    report = await _ingest(db_factory, tmp_path, _fd("LIGUE_1", 2026), _api("LIGUE_1", 2026))
    # Le score API-Football (Rennes 2-2 PSG) concorde avec football-data : aucun désaccord.
    assert not [i for i in report["files"][1]["issues"] if "désaccord" in i]


async def test_playoffs_and_unknown_teams(db_factory: Factory, tmp_path: Path) -> None:
    data = _read(39, 2024)
    first = data["fixtures"][0]
    playoff = {**first, "id": 9_000_001, "d": "2025-06-20"}  # même affiche, autre date
    outsider = {**first, "id": 9_000_002, "h": "Sunderland AFC", "a": "Fulham"}
    data["fixtures"] += [playoff, outsider]
    folder = tmp_path / "api" / "39"
    folder.mkdir(parents=True)
    (folder / "2024.json").write_text(json.dumps(data))

    report = await _ingest(
        db_factory, tmp_path, _fd("EPL", 2024), _api("EPL", 2024, tmp_path / "api")
    )
    assert report["files"][1]["issues"] == ["2 matchs hors championnat (barrages) ignorés"]

    # Une équipe inconnue qui joue toute la saison n'est pas un barrage : fichier rejeté.
    for f in data["fixtures"]:
        if f["h"] == "Fulham":
            f["h"] = "Fulham Inconnu"
    (folder / "2024.json").write_text(json.dumps(data))
    rejected = await _ingest(db_factory, tmp_path, _api("EPL", 2024, tmp_path / "api"))
    assert rejected["files"][0]["status"] == "rejected"
    assert "Fulham Inconnu" in rejected["files"][0]["error"]


async def test_api_football_needs_football_data_first(db_factory: Factory, tmp_path: Path) -> None:
    report = await _ingest(db_factory, tmp_path, _api("EPL", 2024))
    assert report["files"][0]["status"] == "unavailable"
    assert "football-data d'abord" in report["files"][0]["error"]


# --- Téléchargement (API simulée par un transport contrôlé) ---------------------


def _api_transport(
    fixtures: list[dict[str, Any]], calls: list[str], status: Callable[[], int] = lambda: 200
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.url.path}?{request.url.query.decode()}")
        assert request.headers["x-apisports-key"] == "k" * 32
        headers = {"x-ratelimit-requests-remaining": "7000", "x-ratelimit-remaining": "290"}
        if request.url.path == "/status":
            body = {"response": {"requests": {"current": 10, "limit_day": 7500}}, "errors": []}
        elif request.url.path == "/fixtures":
            body = {"response": fixtures, "errors": []}
        else:
            fixture_id = int(request.url.params["fixture"])
            item = next(i for i in fixtures if i["fixture"]["id"] == fixture_id)
            stats = [{"type": "Corner Kicks", "value": 4}, {"type": "Yellow Cards", "value": None}]
            body = {
                "response": [
                    {"team": {"id": t["id"]}, "statistics": stats, "statistics_1h": stats,
                     "statistics_2h": stats}
                    for t in (item["teams"]["home"], item["teams"]["away"])
                ],
                "errors": [],
            }  # fmt: skip
        return httpx.Response(status(), json=body, headers=headers)

    return httpx.MockTransport(handler)


def _raw_fixture(fid: int, home: str, away: str, day: str, hg: int, ag: int) -> dict[str, Any]:
    return {
        "fixture": {"id": fid, "date": f"{day}T19:00:00+00:00", "status": {"short": "FT"}},
        "league": {"round": "Regular Season - 1"},
        "teams": {
            "home": {"id": fid * 10, "name": home},
            "away": {"id": fid * 10 + 1, "name": away},
        },
        "goals": {"home": hg, "away": ag},
        "score": {"halftime": {"home": 0, "away": 0}},
    }


async def test_download_fetches_only_missing_statistics(
    db_factory: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _ingest(db_factory, tmp_path, _fd("EPL", 2024))
    fixtures = [
        _raw_fixture(1, "Manchester United", "Fulham", "2024-08-16", 1, 0),
        _raw_fixture(2, "Ipswich", "Liverpool", "2024-08-17", 0, 2),
    ]
    calls: list[str] = []
    monkeypatch.setattr(service, "api_football_transport", _api_transport(fixtures, calls))
    monkeypatch.setattr(api_football.ApiFootballClient, "__init__", _fast_init)
    settings = make_settings(raw_data_dir=tmp_path / "raw", api_football_key="k" * 32)
    request = IngestionRequest(DataSource.API_FOOTBALL, ["EPL"], [2024])

    messages: list[str] = []
    report = await run_ingestion(db_factory, settings, [request], progress=messages.append)
    assert report["files"][0]["status"] == "ok", report["files"][0]
    assert "    2 matchs terminés, 2 sans statistiques à demander" in messages
    assert [c.split("?")[0] for c in calls] == [
        "/status", "/fixtures", "/fixtures/statistics", "/fixtures/statistics",
    ]  # fmt: skip
    assert all("half=true" in c for c in calls[2:])
    assert await _count(db_factory) == 12  # 2 matchs x 2 équipes x 3 périodes
    assert await _count(db_factory, MatchTeamStats.yellow_cards == 0) == 12

    calls.clear()
    await run_ingestion(db_factory, settings, [request])
    # Déjà complets : seule la liste des matchs est redemandée.
    assert [c.split("?")[0] for c in calls] == ["/status", "/fixtures"]


_original_init = api_football.ApiFootballClient.__init__


def _fast_init(self: api_football.ApiFootballClient, key: str, **kwargs: Any) -> None:
    _original_init(self, key, **{**kwargs, "pause_seconds": 0})


async def test_download_without_key_is_reported(db_factory: Factory, tmp_path: Path) -> None:
    await _ingest(db_factory, tmp_path, _fd("EPL", 2024))
    report = await run_ingestion(
        db_factory,
        make_settings(raw_data_dir=tmp_path / "raw"),
        [IngestionRequest(DataSource.API_FOOTBALL, ["EPL"], [2024])],
    )
    assert report["status"] == "partial"
    assert "FP_API_FOOTBALL_KEY absente" in report["files"][0]["error"]


async def test_rejected_key_stops_without_retry(
    db_factory: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _ingest(db_factory, tmp_path, _fd("EPL", 2024))
    calls: list[str] = []
    monkeypatch.setattr(
        service, "api_football_transport", _api_transport([], calls, status=lambda: 403)
    )
    report = await run_ingestion(
        db_factory,
        make_settings(raw_data_dir=tmp_path / "raw", api_football_key="k" * 32),
        [IngestionRequest(DataSource.API_FOOTBALL, ["EPL"], [2024])],
    )
    assert report["files"][0]["status"] == "unavailable"
    assert "refuse la clé" in report["files"][0]["error"]
    assert calls == ["/status?"]
