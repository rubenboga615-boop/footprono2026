"""Analyse des sources et référentiel (sans base de données).

Les fichiers de ``tests/fixtures`` sont des copies non modifiées de fichiers
réels football-data et Understat.
"""

import argparse
from collections import Counter
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from footprono.football.models import DataSource, OddsTiming
from footprono.ingestion import raw_store
from footprono.ingestion.cli import build_parser, parse_competitions, parse_seasons
from footprono.ingestion.quality import current_season_start
from footprono.ingestion.reference import COMPETITIONS, load_teams, season_code
from footprono.ingestion.sources import football_data, understat

FIXTURES = Path(__file__).parent / "fixtures"


# --- Référentiel -------------------------------------------------------------


def test_season_code() -> None:
    assert season_code(2025) == "2526"
    assert season_code(2099) == "9900"


def test_current_season_start() -> None:
    assert current_season_start(date(2026, 6, 30)) == 2025
    assert current_season_start(date(2026, 7, 1)) == 2026


def test_reference_teams_are_consistent() -> None:
    teams = load_teams()
    codes = {c.code for c in COMPETITIONS}
    assert len(teams) == 165
    assert {t.competition for t in teams} == codes
    assert len({t.name for t in teams}) == len(teams)
    for source in ("football_data", "understat", "api_football"):
        aliases = [a for t in teams for a in t.aliases.get(DataSource(source), ())]
        assert all(DataSource(source) in t.aliases for t in teams), f"alias {source} manquant"
        assert len(set(aliases)) == len(aliases), f"alias {source} en double"


# --- football-data -----------------------------------------------------------


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        ("B365H", ("B365", "1X2", Decimal(0), OddsTiming.PRE, "home")),
        ("B365CA", ("B365", "1X2", Decimal(0), OddsTiming.CLOSE, "away")),
        ("PSD", ("PS", "1X2", Decimal(0), OddsTiming.PRE, "draw")),
        ("P>2.5", ("PS", "OU", Decimal("2.5"), OddsTiming.PRE, "over")),
        ("AvgC<2.5", ("Avg", "OU", Decimal("2.5"), OddsTiming.CLOSE, "under")),
        ("AHh", None),
        ("BbAHh", None),
        ("B365AHH", ("B365", "AH", None, OddsTiming.PRE, "home")),
        ("PCAHA", ("PS", "AH", None, OddsTiming.CLOSE, "away")),
        ("BbMxAHH", ("BbMx", "AH", None, OddsTiming.PRE, "home")),
        ("HomeTeam", None),
    ],
)
def test_classify_odds_column(column: str, expected: object) -> None:
    assert football_data.classify_odds_column(column) == expected


def test_parse_real_football_data_file() -> None:
    content = (FIXTURES / "football-data/2425/E0.csv").read_bytes()
    matches, issues = football_data.parse_csv(content)

    assert len(matches) == 380
    assert all(m.finished for m in matches)
    assert issues.items == []
    first = matches[0]
    assert (first.home_team, first.away_team) == ("Man United", "Fulham")
    assert (first.match_date, first.kickoff_time) == (date(2024, 8, 16), time(20, 0))
    assert (first.home_goals, first.away_goals, first.home_goals_ht) == (1, 0, 0)
    assert first.referee == "R Jones"
    b365 = {
        (q.timing, q.selection): q.price
        for q in first.odds
        if q.bookmaker == "B365" and q.market == "1X2"
    }
    assert b365[(OddsTiming.PRE, "home")] == Decimal("1.6")
    # Seuls les bookmakers retenus sont conservés.
    assert {q.bookmaker for q in first.odds} <= set(football_data.KEPT_BOOKMAKERS)
    assert {q.market for q in first.odds} == {"1X2", "OU", "AH"}
    # Man United contre Fulham : handicap -1 avant match, -0,75 à la clôture.
    ah = {
        (q.timing, q.selection): (q.line, q.price)
        for q in first.odds
        if q.bookmaker == "B365" and q.market == "AH"
    }
    assert ah[(OddsTiming.PRE, "home")] == (Decimal("-1"), Decimal("2.05"))
    assert ah[(OddsTiming.CLOSE, "home")] == (Decimal("-0.75"), Decimal("1.86"))


def test_parse_rejects_invalid_prices_and_reports_them() -> None:
    content = (
        b"Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,HTHG,HTAG,B365H,B365D,B365A\n"
        b"E0,16/08/24,20:00,Arsenal,Chelsea,1,1,0,0,2.1,0,3.5\n"
    )
    matches, issues = football_data.parse_csv(content)
    assert [q.selection for q in matches[0].odds] == ["home", "away"]
    assert len(issues.items) == 1
    assert "B365D" in issues.items[0]


def test_parse_latin1_and_upcoming_match() -> None:
    content = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nF1,01/09/2026,Saint-Étienne,Nîmes,,\n"
    matches, _ = football_data.parse_csv(content.encode("latin-1"))
    assert matches[0].home_team == "Saint-Étienne"
    assert not matches[0].finished
    assert matches[0].kickoff_time is None


# --- Understat ---------------------------------------------------------------


def test_parse_real_understat_export() -> None:
    folder = FIXTURES / "understat/2024/EPL"
    season = understat.parse_export_dir(
        (folder / "matches.csv").read_bytes(), (folder / "team_matches.csv").read_bytes()
    )
    assert len(season.matches) == 380
    assert len(season.team_matches) == 760
    assert season.issues.items == []
    first = season.matches[0]
    assert (first.home_team, first.away_team, first.home_goals) == (
        "Manchester United",
        "Fulham",
        1,
    )
    assert first.kickoff == datetime(2024, 8, 16, 19, 0)
    assert Counter(t.side for t in season.team_matches) == {"h": 380, "a": 380}


def _league_json(matches_key: str = "dates", teams_key: str = "teams") -> dict[str, object]:
    history = {
        "h_a": "h",
        "xG": 1.5,
        "xGA": 0.5,
        "npxG": 1.5,
        "npxGA": 0.5,
        "ppda": {"att": 200, "def": 20},
        "ppda_allowed": {"att": 150, "def": 25},
        "deep": 8,
        "deep_allowed": 3,
        "xpts": 2.1,
        "date": "2025-08-15 19:00:00",
    }
    return {
        matches_key: [
            {
                "id": "1",
                "isResult": True,
                "h": {"id": "1", "title": "Liverpool"},
                "a": {"id": "2", "title": "Bournemouth"},
                "goals": {"h": "4", "a": "2"},
                "datetime": "2025-08-15 19:00:00",
            }
        ],
        teams_key: {"1": {"id": "1", "title": "Liverpool", "history": [history]}},
        "players": [{"id": "10", "player_name": "X"}],
    }


@pytest.mark.parametrize("keys", [("dates", "teams"), ("datesData", "teamsData")])
def test_parse_league_json_detects_keys_by_shape(keys: tuple[str, str]) -> None:
    season = understat.parse_league_json(_league_json(*keys))
    assert season.matches[0].home_team == "Liverpool"
    assert (season.matches[0].home_goals, season.matches[0].away_goals) == (4, 2)
    team = season.team_matches[0]
    assert (team.team, team.side, team.xg, team.ppda_att) == ("Liverpool", "h", Decimal("1.5"), 200)


def test_parse_league_json_rejects_unknown_structure() -> None:
    with pytest.raises(ValueError, match="liste de matchs"):
        understat.parse_league_json({"foo": {}})


# --- Téléchargement ----------------------------------------------------------


async def test_download_returns_content() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"ok"))
    assert await raw_store.download("https://example.test/f.csv", transport=transport) == b"ok"


async def test_download_404_is_unavailable_without_retry() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(404)

    with pytest.raises(raw_store.SourceUnavailableError, match="404"):
        await raw_store.download(
            "https://example.test/f.csv", transport=httpx.MockTransport(handler)
        )
    assert len(calls) == 1


async def test_download_retries_then_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(raw_store.asyncio, "sleep", no_sleep)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503)

    with pytest.raises(raw_store.SourceUnavailableError, match="HTTP 503"):
        await raw_store.download(
            "https://example.test/f.csv", attempts=3, transport=httpx.MockTransport(handler)
        )
    assert len(calls) == 3


# --- Ligne de commande -------------------------------------------------------


def test_parse_seasons() -> None:
    assert parse_seasons("2024") == [2024]
    assert parse_seasons("2016-2018,2020") == [2016, 2017, 2018, 2020]
    for bad in ("abc", "2020-2018", "1800"):
        with pytest.raises(argparse.ArgumentTypeError):
            parse_seasons(bad)


def test_parse_competitions() -> None:
    assert parse_competitions("epl, ligue_1") == ["EPL", "LIGUE_1"]
    with pytest.raises(argparse.ArgumentTypeError, match="MLS"):
        parse_competitions("EPL,MLS")


def test_cli_defaults() -> None:
    args = build_parser().parse_args(["all"])
    assert args.competitions == [c.code for c in COMPETITIONS]
    assert args.seasons is None
    with pytest.raises(SystemExit):
        build_parser().parse_args(["football-data", "--competitions", "MLS"])
