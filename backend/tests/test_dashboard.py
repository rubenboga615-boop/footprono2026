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


async def test_occasions_never_unmeasured_competitions_nor_huge_gaps(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
    monkeypatch: Any,
) -> None:
    """Vérification du 24/11/2026 (Bruges à 50 % contre Liverpool) : pas d'occasion au-delà de
    15 points, ni sur les sélections nationales et les coupes d'Europe."""
    from footprono.bookmaker import dashboard, service
    from footprono.ingestion.reference import CUPS_BY_CODE

    assert set(CUPS_BY_CODE) <= set(dashboard.UNMEASURED_CODES)
    headers = await _login(client)
    await _predict(db_factory, [world["m1"], world["m2"]])
    monkeypatch.setattr(dashboard, "GAP_MAX", 0.05)  # écart du monde de test : +6 points
    service.clear_window_cache()
    body = (await client.get("/api/v1/me/dashboard", headers=headers)).json()
    assert body["engine_above_odds"] == []
    monkeypatch.setattr(dashboard, "GAP_MAX", 0.15)
    monkeypatch.setattr(dashboard, "UNMEASURED_CODES", [*dashboard.UNMEASURED_CODES, "EPL"])
    service.clear_window_cache()
    body = (await client.get("/api/v1/me/dashboard", headers=headers)).json()
    assert body["engine_above_odds"] == []


async def test_bet_history_placed_notifications_then_settled(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    from footprono.notifications import service as notifications

    headers = await _login(client)
    r = await client.post(
        "/api/v1/bets", json={"stake": 1_000, "selections": [_sel(world["m1"], "1X2", "home")]},
        headers=headers,
    )  # fmt: skip
    bet_id = r.json()["id"]
    async with db_factory() as session:
        notifications.add(
            session, world["user_id"], "bet_live", "Tout se joue sur Lens", "…", {"bet_id": bet_id}
        )
        notifications.add(
            session, world["user_id"], "bet_live", "But", "…",
            {"events": [{"type": "changed", "bet_id": bet_id, "match_id": world["m1"]}]},
        )  # fmt: skip
        notifications.add(session, world["user_id"], "bet_live", "Autre pari", "…", {"bet_id": 999})
        await session.commit()
    assert (await client.get(f"/api/v1/bets/{bet_id}/history")).status_code == 401
    events = (await client.get(f"/api/v1/bets/{bet_id}/history", headers=headers)).json()["events"]
    assert [e["text"] for e in events] == ["placé", "Tout se joue sur Lens", "But"]
    assert (await client.get("/api/v1/bets/999999/history", headers=headers)).status_code == 404
