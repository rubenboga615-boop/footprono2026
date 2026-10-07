"""Vérification des cotes des coupes d'Europe (API-Football simulée)."""

from datetime import date
from typing import Any

import httpx
import pytest

from footprono.ingestion import cup_odds_check, service

from .conftest import make_settings


def _fixture(fid: int, home: str, away: str) -> dict[str, Any]:
    return {
        "fixture": {"id": fid, "date": "2026-10-21T19:00:00+00:00"},
        "teams": {"home": {"name": home}, "away": {"name": away}},
    }


def _handler(request: httpx.Request) -> httpx.Response:
    path, league = request.url.path, request.url.params.get("league")
    if path.endswith("/status"):
        return httpx.Response(
            200, json={"response": {"requests": {"limit_day": 7500, "current": 10}}}
        )
    if path.endswith("/fixtures"):
        return httpx.Response(200, json={"response": [_fixture(10, "Arsenal", "PSG")]})
    assert path.endswith("/odds")
    if league == "848":  # Conférence League : pas encore de cotes
        return httpx.Response(200, json={"response": [], "paging": {"current": 1, "total": 0}})
    books = [
        {"name": "Bet365", "bets": [
            {"name": "Match Winner", "values": [{"value": "Home", "odd": "2.10"}]},
            {"name": "Double Chance", "values": [{"value": "Home/Draw", "odd": "1.30"}]},
        ]},
        {"name": "Unibet", "bets": [
            {"name": "Match Winner", "values": [{"value": "Home", "odd": "2.05"}]},
        ]},
    ]  # fmt: skip
    return httpx.Response(200, json={
        "response": [
            {"fixture": {"id": 10}, "update": "2026-10-07T08:00:00+00:00", "bookmakers": books},
        ],
        "paging": {"current": 1, "total": 1},
    })  # fmt: skip


async def test_cup_odds_check_reports_bookmakers_and_markets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "api_football_transport", httpx.MockTransport(_handler))
    lines: list[str] = []
    report = await cup_odds_check.check_cup_odds(
        make_settings(api_football_key="cle-test"), [2, 848], 2026, lines.append
    )
    ucl = report["leagues"]["Ligue des Champions"]
    assert ucl["fixtures_with_odds_page1"] == 1
    assert ucl["our_bookmakers"] == {"Bet365": ["Double Chance", "Match Winner"]}
    assert ucl["missing_bookmakers"] == ["1xBet", "Pinnacle"]
    assert report["leagues"]["Conférence League"]["fixtures_with_odds_page1"] == 0
    assert any("AUCUNE COTE" in line for line in lines)
    assert report["requests"] == 4


def test_cup_season() -> None:
    assert cup_odds_check.cup_season(date(2026, 10, 7)) == 2026
    assert cup_odds_check.cup_season(date(2027, 3, 1)) == 2026


async def test_without_key() -> None:
    report = await cup_odds_check.check_cup_odds(make_settings(), [2], 2026, print)
    assert report["status"] == "unavailable"
