"""Cotes des bookmakers pour les matchs à venir (API-Football simulée)."""

from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.football.models import BookmakerOdds, DataSource, Match
from footprono.ingestion import service
from footprono.ingestion.live import collect_odds
from footprono.ingestion.service import IngestionRequest, run_ingestion
from footprono.ingestion.sources import api_football
from footprono.ingestion.sources.api_football_odds import map_bet, parse_odds_page

from .conftest import make_settings

FIXTURES = Path(__file__).parent / "fixtures"
Factory = async_sessionmaker[AsyncSession]


@pytest.mark.parametrize(
    ("bet", "value", "expected"),
    [
        ("Match Winner", "Home", ("1X2", "", "home")),
        ("Match Winner", "Draw", ("1X2", "", "draw")),
        ("Double Chance", "Draw/Away", ("DC", "", "X2")),
        ("Goals Over/Under", "Over 2.5", ("OU", "2.5", "over")),
        ("Goals Over/Under First Half", "Under 0.5", ("HT_OU", "0.5", "under")),
        ("Both Teams Score", "Yes", ("BTTS", "", "yes")),
        ("HT/FT Double", "Draw/Home", ("HTFT", "", "draw/home")),
        ("Exact Score", "2:1", ("CS", "", "2-1")),
        ("Exact Score", "7:0", None),
        ("Corners Over Under", "Over 9.5", ("CORNERS_OU", "9.5", "over")),
        ("Total - Away", "Over 1.5", ("TEAM_OU_AWAY", "1.5", "over")),
        ("Highest Scoring Half", "2nd Half", ("HIGHEST_HALF", "", "second")),
        ("Asian Handicap", "Home -0.5", None),  # sens de la ligne à vérifier : non traduit
        ("Goals Over/Under", "Over", None),
    ],
)
def test_map_bet(bet: str, value: str, expected: tuple[str, str, str] | None) -> None:
    assert map_bet(bet, value) == expected


def _odds_item(fixture_id: int, book: str, home: str) -> dict[str, Any]:
    return {
        "fixture": {"id": fixture_id},
        "update": "2026-10-08T10:00:00+00:00",
        "bookmakers": [
            {
                "id": 11,
                "name": book,
                "bets": [
                    {
                        "name": "Match Winner",
                        "values": [
                            {"value": "Home", "odd": home},
                            {"value": "Draw", "odd": "3.40"},
                            {"value": "Away", "odd": "4.10"},
                        ],
                    },
                    {"name": "Player to Score", "values": [{"value": "X", "odd": "5.00"}]},
                    {"name": "Goals Over/Under", "values": [{"value": "Over 2.5", "odd": "1"}]},
                ],
            }
        ],
    }


def test_parse_odds_page_skips_invalid_prices() -> None:
    body = {"response": [_odds_item(7, "1xBet", "1.85")], "paging": {"current": 1, "total": 2}}
    quotes, current, total = parse_odds_page(body)
    assert (current, total) == (1, 2)
    assert len(quotes) == 4  # la cote à 1,00 est écartée
    assert quotes[0].price == Decimal("1.85")
    assert quotes[0].updated_at is not None


def _transport(fixtures: list[int], home_price: list[str], calls: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        headers = {"x-ratelimit-requests-remaining": "7000", "x-ratelimit-remaining": "290"}
        if request.url.path == "/status":
            body: Any = {"response": {"requests": {"current": 1, "limit_day": 7500}}}
        elif request.url.path == "/odds/bookmakers":
            body = {"response": [{"id": 11, "name": "1xBet"}, {"id": 8, "name": "Bet365"}]}
        elif (
            request.url.params.get("league") == "39" and request.url.params.get("bookmaker") == "11"
        ):
            items = [_odds_item(f, "1xBet", home_price[0]) for f in fixtures]
            body = {"response": items, "paging": {"current": 1, "total": 1}}
        else:
            body = {"response": [], "paging": {"current": 1, "total": 1}}
        return httpx.Response(200, json={**body, "errors": []}, headers=headers)

    return httpx.MockTransport(handler)


_original_init = api_football.ApiFootballClient.__init__


def _fast_init(self: api_football.ApiFootballClient, key: str, **kwargs: Any) -> None:
    _original_init(self, key, **{**kwargs, "pause_seconds": 0})


async def test_collect_odds_keeps_only_changes(
    db_factory: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, client: AsyncClient
) -> None:
    await run_ingestion(
        db_factory,
        make_settings(raw_data_dir=tmp_path / "raw"),
        [IngestionRequest(DataSource.FOOTBALL_DATA, ["EPL"], [2024], FIXTURES / "football-data")],
    )
    async with db_factory() as session:
        ids = list(await session.scalars(select(Match.id).order_by(Match.id).limit(2)))
        for n, match_id in enumerate(ids):
            await session.execute(
                update(Match).where(Match.id == match_id).values(api_football_id=5000 + n)
            )
        await session.commit()

    price = ["1.85"]
    calls: list[str] = []
    monkeypatch.setattr(
        service, "api_football_transport", _transport([5000, 5001, 9999], price, calls)
    )
    monkeypatch.setattr(api_football.ApiFootballClient, "__init__", _fast_init)
    settings = make_settings(raw_data_dir=tmp_path / "raw", api_football_key="k" * 32)

    async with db_factory() as session:
        first = await collect_odds(session, settings)
    assert first["status"] == "ok"
    assert first["matches"] == 2
    assert first["changed"] == 8  # 2 matchs x 4 cotes valides
    assert "bookmaker « Pinnacle » absent d'API-Football : non relevé" in first["issues"]
    assert "1 matchs API-Football inconnus en base : ignorés" in first["issues"]
    assert first["unmapped_bets"] == ["Player to Score"]
    # 5 championnats x 2 bookmakers trouvés = 10 pages, + la liste des bookmakers.
    assert calls.count("/odds") == 10

    async with db_factory() as session:
        again = await collect_odds(session, settings)
    assert again["changed"] == 0  # rien n'a bougé : aucune ligne ajoutée

    price[0] = "1.90"
    async with db_factory() as session:
        moved = await collect_odds(session, settings)
        total = await session.scalar(select(func.count()).select_from(BookmakerOdds))
    assert moved["changed"] == 2  # seule la cote domicile a bougé, sur 2 matchs
    assert total == 10  # historique conservé

    response = await client.get(f"/api/v1/matches/{ids[0]}/bookmaker-odds")
    assert response.status_code == 200
    rows = {(r["bet"], r["value"]): r for r in response.json()}
    home = rows[("Match Winner", "Home")]
    assert Decimal(home["price"]) == Decimal("1.90")
    assert (home["market"], home["line"], home["selection"]) == ("1X2", None, "home")
    assert rows[("Player to Score", "X")]["market"] is None
