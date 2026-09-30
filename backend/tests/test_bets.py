"""Bookmaker virtuel : prise de paris aux cotes réelles."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.accounts import service as accounts
from footprono.accounts.models import Wallet
from footprono.football.models import BookmakerOdds, DataSource, Match, MatchStatus
from footprono.ingestion.service import IngestionRequest, run_ingestion

from .conftest import make_settings

FIXTURES = Path(__file__).parent / "fixtures"
Factory = async_sessionmaker[AsyncSession]
NOW = datetime.now(UTC)


def quote(match_id: int, book: str, bet: str, value: str, price: str, seen: datetime) -> Any:
    return BookmakerOdds(
        match_id=match_id, fetched_at=seen, last_seen_at=seen, bookmaker=book, bet=bet,
        value=value, price=Decimal(price),
    )  # fmt: skip


@pytest.fixture
async def world(db_factory: Factory, tmp_path: Path) -> dict[str, Any]:
    """Deux matchs à venir cotés par 1xBet (et Bet365 pour un marché), un joueur."""
    await run_ingestion(
        db_factory,
        make_settings(raw_data_dir=tmp_path),
        [IngestionRequest(DataSource.FOOTBALL_DATA, ["EPL"], [2024], FIXTURES / "football-data")],
    )
    seen = NOW - timedelta(hours=1)
    async with db_factory() as session:
        ids = list(await session.scalars(select(Match.id).order_by(Match.id.desc()).limit(3)))
        await session.execute(
            update(Match)
            .where(Match.id.in_(ids))
            .values(
                status=MatchStatus.SCHEDULED, home_goals=None, away_goals=None,
                kickoff_at=NOW + timedelta(days=1), api_status="NS",
            )
        )  # fmt: skip
        m1, m2, started = ids
        await session.execute(
            update(Match).where(Match.id == started).values(kickoff_at=NOW - timedelta(minutes=5))
        )
        for m in (m1, m2, started):
            session.add_all(
                [
                    quote(m, "1xBet", "Match Winner", "Home", "1.85", seen),
                    quote(m, "1xBet", "Match Winner", "Draw", "3.60", seen),
                    quote(m, "1xBet", "Match Winner", "Away", "4.20", seen),
                    quote(m, "Bet365", "Goals Over/Under", "Over 2.5", "1.90", seen),
                    quote(m, "Pinnacle", "Both Teams Score", "Yes", "1.70", seen),
                ]
            )
        user = await accounts.register(
            session, make_settings(), phone="+22997111111", password="12345678",
            display_name="Kofi", country="TG", adult=True,
        )  # fmt: skip
        await session.commit()
        return {"m1": m1, "m2": m2, "started": started, "user_id": user.id}


async def _login(client: AsyncClient) -> dict[str, str]:
    r = await client.post(
        "/api/v1/auth/login", json={"phone": "+22997111111", "password": "12345678"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _sel(match_id: int, market: str, sel: str, line: str = "", **extra: Any) -> dict[str, Any]:
    return {"match_id": match_id, "market": market, "line": line, "selection": sel, **extra}


async def test_offer_uses_real_odds_only(world: dict[str, Any], client: AsyncClient) -> None:
    offer = (await client.get(f"/api/v1/matches/{world['m1']}/offer")).json()
    keys = {(o["market"], o["line"], o["selection"]): o for o in offer}
    assert keys[("1X2", None, "home")]["odds"] == "1.850"
    assert keys[("1X2", None, "home")]["bookmaker"] == "1xBet"
    assert keys[("OU", "2.5", "over")]["bookmaker"] == "Bet365"  # secours
    assert ("BTTS", None, "yes") not in keys  # Pinnacle : référence interne, non jouable


async def test_place_single_and_combo(
    world: dict[str, Any], client: AsyncClient, db_factory: Factory
) -> None:
    headers = await _login(client)
    single = await client.post(
        "/api/v1/bets",
        json={"stake": 5000, "selections": [_sel(world["m1"], "1X2", "home", odds="1.85")]},
        headers=headers,
    )
    assert single.status_code == 201, single.text
    body = single.json()
    assert (body["kind"], body["total_odds"], body["potential_payout"]) == ("single", "1.850", 9250)
    assert body["selections"][0]["bookmaker"] == "1xBet"

    combo = await client.post(
        "/api/v1/bets",
        json={
            "stake": 1000,
            "selections": [
                _sel(world["m1"], "1X2", "draw"),
                _sel(world["m2"], "OU", "over", "2.5"),
            ],
        },
        headers=headers,
    )
    assert combo.status_code == 201, combo.text
    assert combo.json()["total_odds"] == "6.840"  # 3,60 x 1,90
    assert combo.json()["potential_payout"] == 6840

    async with db_factory() as session:
        wallet = await session.get(Wallet, world["user_id"])
    assert wallet is not None
    assert wallet.balance == 100_000 - 5000 - 1000
    history = (await client.get("/api/v1/bets", headers=headers)).json()
    assert [b["kind"] for b in history] == ["combo", "single"]


@pytest.mark.parametrize(
    ("case", "status", "fragment"),
    [
        ("same_match", 400, "même match"),
        ("odds_dropped", 409, "la cote a baissé"),
        ("not_offered", 400, "aucune cote réelle"),
        ("reference_only", 400, "aucune cote réelle"),
        ("started", 400, "déjà commencé"),
        ("too_small", 400, "mise minimale"),
        ("too_big", 409, "solde insuffisant"),
    ],
)
async def test_refused_bets(
    world: dict[str, Any], client: AsyncClient, case: str, status: int, fragment: str
) -> None:
    m1: Callable[..., dict[str, Any]] = lambda *a, **k: _sel(world["m1"], *a, **k)  # noqa: E731
    bodies = {
        "same_match": {"stake": 500, "selections": [m1("1X2", "home"), m1("OU", "over", "2.5")]},
        "odds_dropped": {"stake": 500, "selections": [m1("1X2", "home", odds="1.95")]},
        "not_offered": {"stake": 500, "selections": [m1("OU", "over", "3.5")]},
        "reference_only": {"stake": 500, "selections": [m1("BTTS", "yes")]},
        "started": {"stake": 500, "selections": [_sel(world["started"], "1X2", "home")]},
        "too_small": {"stake": 50, "selections": [m1("1X2", "home")]},
        "too_big": {"stake": 100_001, "selections": [m1("1X2", "home")]},
    }
    r = await client.post("/api/v1/bets", json=bodies[case], headers=await _login(client))
    assert r.status_code == status, r.text
    assert fragment in r.json()["error"]["message"]


async def test_withdrawn_odds_are_not_playable(
    world: dict[str, Any], client: AsyncClient, db_factory: Factory
) -> None:
    # Nouveau relevé 1xBet sans la cote « Home » : elle a été retirée.
    later = NOW - timedelta(minutes=10)
    async with db_factory() as session:
        await session.execute(
            update(BookmakerOdds)
            .where(
                BookmakerOdds.match_id == world["m1"],
                BookmakerOdds.bookmaker == "1xBet",
                BookmakerOdds.value != "Home",
            )
            .values(last_seen_at=later)
        )
        await session.commit()
    offer = (await client.get(f"/api/v1/matches/{world['m1']}/offer")).json()
    selections = {(o["market"], o["selection"]) for o in offer}
    assert ("1X2", "home") not in selections
    assert ("1X2", "draw") in selections
