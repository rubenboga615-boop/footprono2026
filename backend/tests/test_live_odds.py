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
from footprono.ingestion.reference import COMPETITIONS
from footprono.ingestion.service import IngestionRequest, run_ingestion
from footprono.ingestion.sources import api_football
from footprono.ingestion.sources.api_football_odds import (
    OddsQuote,
    handicap_diagnostics,
    map_bet,
    parse_odds_page,
)

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
        ("Clean Sheet - Away", "No", ("CLEAN_SHEET", "", "away_no")),
        ("Win To Nil", "Home", ("WIN_TO_NIL", "", "home")),
        ("Results/Both Teams Score", "Draw/No", ("1X2_BTTS", "", "draw/no")),
        ("Result/Total Goals", "Away/Over 4.5", ("1X2_OU", "4.5", "away/over")),
        ("Total Goals/Both Teams To Score", "o/yes 2.5", ("OU_BTTS", "2.5", "over/yes")),
        ("Winning Margin", "2 by 4+", ("MARGIN", "", "away+4")),
        ("Winning Margin", "1 by 1", ("MARGIN", "", "home+1")),
        ("Winning Margin", "Score Draw", None),
        # Ligne du domicile pour les deux côtés (vérifié sur cotes réelles).
        ("Asian Handicap", "Home -0.75", ("AH", "-0.75", "home")),
        ("Asian Handicap", "Away -0.75", ("AH", "-0.75", "away")),
        ("Asian Handicap", "Away +0", ("AH", "0", "away")),
        ("Asian Handicap", "Home -3.5", None),
        ("Handicap Result", "Draw -1", ("EH", "-1", "draw")),
        ("Handicap Result", "Away +2", ("EH", "2", "away")),
        ("Handicap Result", "Away -5", None),
        ("Goals Over/Under", "Over", None),
    ],
)
def test_map_bet(bet: str, value: str, expected: tuple[str, str, str] | None) -> None:
    assert map_bet(bet, value) == expected


def test_handicap_diagnostics_finds_the_convention() -> None:
    def q(bet: str, value: str, price: str) -> OddsQuote:
        return OddsQuote(1, "Pinnacle", bet, value, Decimal(price), None)

    quotes = [
        # Chaque équipe avec son propre handicap : Home -0.5 ↔ Away +0.5.
        q("Asian Handicap", "Home -0.5", "1.90"),
        q("Asian Handicap", "Away +0.5", "1.98"),
        q("Asian Handicap", "Home +0.5", "1.40"),
        q("Asian Handicap", "Away -0.5", "3.00"),
        q("Asian Handicap", "Home +0", "1.60"),
        q("Asian Handicap", "Away +0", "2.40"),
    ]
    check = handicap_diagnostics(quotes)["Asian Handicap"]
    assert check["own"] == {"pairs": 3, "share_plausible": 1.0}
    assert check["home_line"]["share_plausible"] < 1.0


def _odds_item(
    fixture_id: int, book: str, home: str, updated: str = "2026-10-08T10:00:00+00:00"
) -> dict[str, Any]:
    return {
        "fixture": {"id": fixture_id},
        "update": updated,
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


def _transport(
    fixtures: list[int], home_price: list[str], calls: list[str], updated: list[str] | None = None
) -> httpx.MockTransport:
    updated = updated or ["2026-10-08T10:00:00+00:00"]

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
            items = [_odds_item(f, "1xBet", home_price[0], updated[0]) for f in fixtures]
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
    stamp = ["2026-10-08T10:00:00+00:00"]
    calls: list[str] = []
    monkeypatch.setattr(
        service, "api_football_transport", _transport([5000, 5001, 9999], price, calls, stamp)
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
    assert first["unmapped_bets"] == {"Player to Score": {"partial": False, "values": ["X"]}}
    # Chaque championnat x 2 bookmakers trouvés = une page chacun, + la liste des bookmakers.
    assert calls.count("/odds") == 2 * len(COMPETITIONS)

    stamp[0] = "2026-10-08T13:00:00+00:00"  # la source confirme les mêmes prix plus tard
    async with db_factory() as session:
        again = await collect_odds(session, settings)
        stamps = set(await session.scalars(select(BookmakerOdds.source_updated_at)))
    assert again["changed"] == 0  # rien n'a bougé : aucune ligne ajoutée
    # … mais la date de mise à jour affichée suit la source.
    assert {s.isoformat() for s in stamps} == {"2026-10-08T13:00:00+00:00"}

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
