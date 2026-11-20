"""Tableau de bord « Aujourd'hui » (nouveau visage, étape B, 20/11/2026)."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .test_bets import _login, _sel, world  # noqa: F401 (fixture partagée)
from .test_montante import _predict

Factory = async_sessionmaker[AsyncSession]


async def test_dashboard_curve_figures_and_engine_above_odds(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    assert (await client.get("/api/v1/me/dashboard")).status_code == 401
    headers = await _login(client)
    await _predict(db_factory, [world["m1"], world["m2"]])
    r = await client.post(
        "/api/v1/bets", json={"stake": 2_000, "selections": [_sel(world["m1"], "1X2", "home")]},
        headers=headers,
    )  # fmt: skip
    assert r.status_code == 201, r.text

    body = (await client.get("/api/v1/me/dashboard", headers=headers)).json()
    assert body["balance"] == body["curve"][-1]["balance"]
    assert body["stakes"]["week"] == 2_000
    assert body["last_30_days"]["settled"] == 0  # pari encore en cours
    assert body["engine"]["selections"] == 0
    # Moteur 60 % contre 1 / 1,85 = 54 % sur la victoire à domicile : +6 points, un par match ;
    # nul (25 % contre 28 %) et plus de 2,5 buts (50 % contre 53 %) n'y sont pas.
    above = body["engine_above_odds"]
    assert {a["match_id"] for a in above} == {world["m1"], world["m2"]}
    assert all((a["market"], a["selection"]) == ("1X2", "home") for a in above)
    assert all(a["engine"] - a["implied"] >= body["gap_min"] for a in above)
