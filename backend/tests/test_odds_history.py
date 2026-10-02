"""Mouvement des cotes : cote d'ouverture dans l'offre, historique des changements."""

from datetime import timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .test_bets import NOW, quote, world  # noqa: F401 (fixture)


async def test_offer_shows_opening_odds_and_history(
    db_factory: async_sessionmaker[AsyncSession],
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
) -> None:
    m1 = world["m1"]
    url = f"/api/v1/matches/{m1}/offer"
    before = {o["selection"]: o for o in (await client.get(url)).json() if o["market"] == "1X2"}
    # Une seule cote relevée : ouverture = cote actuelle.
    assert before["home"]["opening_odds"] == before["home"]["odds"] == "1.850"

    async with db_factory() as session:
        moved = quote(m1, "1xBet", "Match Winner", "Home", "1.75", NOW - timedelta(minutes=10))
        session.add(moved)
        await session.commit()

    home = next(
        o
        for o in (await client.get(url)).json()
        if (o["market"], o["selection"]) == ("1X2", "home")
    )
    assert home["odds"] == "1.750"
    assert home["opening_odds"] == "1.850"
    assert home["checked_at"] is not None  # dernier relevé ; la mise à jour source peut manquer
    assert "source_updated_at" in home

    r = await client.get(
        f"/api/v1/matches/{m1}/odds-history", params={"market": "1X2", "selection": "home"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bookmaker"] == "1xBet"
    assert [p["odds"] for p in body["points"]] == ["1.850", "1.750"]
    times = [p["at"] for p in body["points"]]
    assert times == sorted(times)

    absent = await client.get(
        f"/api/v1/matches/{m1}/odds-history", params={"market": "1X2", "selection": "nope"}
    )
    assert absent.status_code == 404
    locked = await client.get(
        f"/api/v1/matches/{m1}/odds-history",
        params={"market": "AH", "line": "-0.5", "selection": "home"},
    )
    assert locked.status_code == 403  # marché Premium, sans connexion
