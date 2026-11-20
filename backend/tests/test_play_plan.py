"""Mon plan de jeu et alertes de cote (maquettes 29 et 30 du nouveau visage, 20/11/2026)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.bookmaker import odds_alerts, play_plan
from footprono.bookmaker.play_models import OddsAlert, PlayPlan
from footprono.notifications.models import Notification

from .test_bets import NOW, _login, _sel, quote, world  # noqa: F401 (fixture partagée)
from .test_montante import _predict

Factory = async_sessionmaker[AsyncSession]


def test_week_starts_monday_midnight_local_time() -> None:
    # Jeudi 19/11/2026 23:30 UTC = vendredi 0 h 30 au Bénin (UTC+1) : semaine du lundi 16.
    now = datetime(2026, 11, 19, 23, 30, tzinfo=UTC)
    assert play_plan.week_start("BJ", now) == datetime(2026, 11, 15, 23, 0, tzinfo=UTC)
    assert play_plan.week_start("CI", now) == datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
    # Dimanche 23 h 30 UTC = lundi 0 h 30 au Bénin : nouvelle semaine.
    sunday = datetime(2026, 11, 22, 23, 30, tzinfo=UTC)
    assert play_plan.week_start("BJ", sunday) == datetime(2026, 11, 22, 23, 0, tzinfo=UTC)


async def test_plan_stricter_now_looser_after_24_hours(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    assert (await client.get("/api/v1/me/play-plan")).status_code == 401
    headers = await _login(client)
    body = (await client.get("/api/v1/me/play-plan", headers=headers)).json()
    assert body["weekly_budget"] is None
    assert body["week"]["staked"] == 0

    plan = {"weekly_budget": 5_000, "loss_limit": 3_000, "max_stake": 2_000, "reminder": True}
    body = (await client.put("/api/v1/me/play-plan", json=plan, headers=headers)).json()
    assert {k: body[k] for k in plan} == plan  # plus strict qu'« aucune limite » : tout de suite
    assert body["pending"] is None

    # Relever le budget, retirer la mise maximale : dans 24 h ; baisser la perte : tout de suite.
    r = await client.put(
        "/api/v1/me/play-plan",
        json={"weekly_budget": 8_000, "max_stake": None, "loss_limit": 2_500},
        headers=headers,
    )
    body = r.json()
    assert (body["weekly_budget"], body["max_stake"], body["loss_limit"]) == (5_000, 2_000, 2_500)
    assert body["pending"] == {"weekly_budget": 8_000, "max_stake": None}
    assert body["pending_applies_at"] is not None

    async with db_factory() as session:
        p = await session.get(PlayPlan, world["user_id"])
        assert p is not None
        p.pending_at = datetime.now(UTC) - timedelta(hours=25)
        await session.commit()
    body = (await client.get("/api/v1/me/play-plan", headers=headers)).json()
    assert (body["weekly_budget"], body["max_stake"], body["pending"]) == (8_000, None, None)

    bad = await client.put("/api/v1/me/play-plan", json={"max_stake": 50}, headers=headers)
    assert bad.status_code == 422


async def test_plan_refuses_bets_beyond_its_limits(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
) -> None:
    headers = await _login(client)
    await client.put(
        "/api/v1/me/play-plan", json={"weekly_budget": 3_000, "max_stake": 2_000}, headers=headers
    )

    async def bet(stake: int) -> Any:
        return await client.post(
            "/api/v1/bets",
            json={"stake": stake, "selections": [_sel(world["m1"], "1X2", "home")]},
            headers=headers,
        )

    r = await bet(2_500)
    assert r.status_code == 400
    assert "2 000" in r.json()["error"]["message"].replace("\u202f", " ")
    assert (await bet(2_000)).status_code == 201
    r = await bet(1_500)  # 2 000 + 1 500 > 3 000
    assert r.status_code == 400
    assert "Il reste 1" in r.json()["error"]["message"]
    assert (await bet(1_000)).status_code == 201

    body = (await client.get("/api/v1/me/play-plan", headers=headers)).json()
    assert body["week"]["staked"] == 3_000
    dash = (await client.get("/api/v1/me/dashboard", headers=headers)).json()
    assert dash["play_plan"]["weekly_budget"] == 3_000
    assert dash["play_plan"]["week"]["staked"] == 3_000


async def test_pause_blocks_bets_and_cannot_be_shortened(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
) -> None:
    headers = await _login(client)
    assert (
        await client.post("/api/v1/me/play-plan/pause", json={"days": 3}, headers=headers)
    ).status_code == 422
    week = (
        await client.post("/api/v1/me/play-plan/pause", json={"days": 7}, headers=headers)
    ).json()["pause_until"]
    day = (
        await client.post("/api/v1/me/play-plan/pause", json={"days": 1}, headers=headers)
    ).json()["pause_until"]
    assert day == week  # une pause plus courte ne raccourcit pas celle en cours
    r = await client.post(
        "/api/v1/bets",
        json={"stake": 500, "selections": [_sel(world["m1"], "1X2", "home")]},
        headers=headers,
    )
    assert r.status_code == 400
    assert r.json()["error"]["message"].startswith("Pause en cours")


async def test_loss_limit_counts_settled_bets_of_the_week(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    from footprono.bookmaker.models import Bet

    headers = await _login(client)
    await client.put("/api/v1/me/play-plan", json={"loss_limit": 1_000}, headers=headers)
    r = await client.post(
        "/api/v1/bets",
        json={"stake": 1_000, "selections": [_sel(world["m1"], "1X2", "home")]},
        headers=headers,
    )
    assert r.status_code == 201
    async with db_factory() as session:  # pari perdu, réglé cette semaine
        await session.execute(
            update(Bet)
            .where(Bet.id == r.json()["id"])
            .values(status="settled", outcome="lost", payout=0, settled_at=datetime.now(UTC))
        )
        await session.commit()
    r = await client.post(
        "/api/v1/bets",
        json={"stake": 500, "selections": [_sel(world["m2"], "1X2", "home")]},
        headers=headers,
    )
    assert r.status_code == 400
    assert "Limite de perte" in r.json()["error"]["message"]


@pytest.fixture
def awake(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les tests ne dépendent pas de l'heure : jamais la nuit du joueur."""
    monkeypatch.setattr(odds_alerts, "quiet", lambda country, now: False)


async def test_selection_alert_fires_once_when_odds_reach_target(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
    awake: None,
) -> None:
    headers = await _login(client)
    await _predict(db_factory, [world["m1"], world["m2"]])
    alert = _sel(world["m1"], "1X2", "home")
    too_low = await client.post(
        "/api/v1/me/odds-alerts", json=alert | {"target_odds": "1.80"}, headers=headers
    )
    assert too_low.status_code == 400
    assert "déjà à 1,85" in too_low.json()["error"]["message"]
    r = await client.post(
        "/api/v1/me/odds-alerts", json=alert | {"target_odds": "1.95"}, headers=headers
    )
    assert r.status_code == 201, r.text

    async with db_factory() as session:
        assert await odds_alerts.check(session) == 0  # toujours 1,85
    async with db_factory() as session:
        session.add(quote(world["m1"], "1xBet", "Match Winner", "Home", "1.97", NOW))
        await session.commit()
    async with db_factory() as session:
        assert await odds_alerts.check(session) == 1
    async with db_factory() as session:
        assert await odds_alerts.check(session) == 0  # une seule fois
        note = await session.scalar(select(Notification).where(Notification.kind == "odds_alert"))
        assert note is not None
        assert "1,85 → 1,97" in note.body
        assert "Chance du moteur : 60 %" in note.body
        a = await session.scalar(select(OddsAlert))
        assert a is not None
        assert (a.active, a.triggered_at is not None) == (False, True)

    body = (await client.get("/api/v1/me/odds-alerts", headers=headers)).json()
    assert body["alerts"][0]["active"] is False
    assert [h["odds"] for h in body["hits"]] == [1.97]
    assert body["hits"][0]["engine"] == 0.6


async def test_gap_alert_one_notification_for_several_matches(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
    awake: None,
) -> None:
    headers = await _login(client)
    await _predict(db_factory, [world["m1"], world["m2"]])
    bad = await client.put("/api/v1/me/odds-alerts/gap", json={"min_gap": 0.07}, headers=headers)
    assert bad.status_code == 400
    # 60 % contre 1 / 1,85 = 54 % : +6 points, assez pour 5, pas pour 8.
    r = await client.put("/api/v1/me/odds-alerts/gap", json={"min_gap": 0.08}, headers=headers)
    assert r.status_code == 200
    async with db_factory() as session:
        assert await odds_alerts.check(session) == 0
    await client.put("/api/v1/me/odds-alerts/gap", json={"min_gap": 0.05}, headers=headers)
    async with db_factory() as session:
        assert await odds_alerts.check(session) == 1  # une notification pour les deux matchs
        assert await odds_alerts.check(session) == 0
        notes = (
            await session.scalars(select(Notification).where(Notification.kind == "odds_alert"))
        ).all()
        assert len(notes) == 1
        assert "et 1 autre match" in notes[0].body
        assert "pari" not in notes[0].body.lower()
    body = (await client.get("/api/v1/me/odds-alerts", headers=headers)).json()
    assert body["gap"] == {"id": body["gap"]["id"], "min_gap": 0.05, "active": True}
    assert {h["match_id"] for h in body["hits"]} == {world["m1"], world["m2"]}


async def test_alert_owner_only_and_delete(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    headers = await _login(client)
    await _predict(db_factory, [world["m1"]])
    r = await client.post(
        "/api/v1/me/odds-alerts",
        json=_sel(world["m1"], "1X2", "home") | {"target_odds": "2.10"},
        headers=headers,
    )
    aid = r.json()["id"]
    off = await client.patch(
        f"/api/v1/me/odds-alerts/{aid}", json={"active": False}, headers=headers
    )
    assert off.json() == {"id": aid, "active": False}
    assert (
        await client.patch("/api/v1/me/odds-alerts/999999", json={"active": True}, headers=headers)
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/me/odds-alerts/{aid}", headers=headers)
    ).status_code == 204
    assert (await client.get("/api/v1/me/odds-alerts", headers=headers)).json()["alerts"] == []


async def test_followed_teams(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    from footprono.football.models import Match

    headers = await _login(client)
    assert (await client.get("/api/v1/me/followed-teams")).status_code == 401
    async with db_factory() as session:
        m = await session.get(Match, world["m1"])
        assert m is not None
        team = m.home_team_id
    assert (
        await client.put(f"/api/v1/me/followed-teams/{team}", headers=headers)
    ).status_code == 204
    assert (
        await client.put(f"/api/v1/me/followed-teams/{team}", headers=headers)
    ).status_code == 204
    assert (await client.get("/api/v1/me/followed-teams", headers=headers)).json() == [team]
    assert (
        await client.put("/api/v1/me/followed-teams/999999", headers=headers)
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/me/followed-teams/{team}", headers=headers)
    ).status_code == 204
    assert (await client.get("/api/v1/me/followed-teams", headers=headers)).json() == []
