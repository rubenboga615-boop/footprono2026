"""Coupon en direct (maquettes D8 à D15 validées le 13/11/2026) : fenêtres, cotes en direct,
propositions par profil, combinés de plusieurs matchs, pari placé en direct."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.bookmaker import live_coupons
from footprono.bookmaker.models import Bet, BetSelection
from footprono.football.models import LiveSnapshot, Match, MatchEvent
from footprono.predictions.publication import LIVE_KEY, set_flag

from .conftest import TEST_REDIS_URL
from .test_bets import _login, _sel, world  # noqa: F401 (fixture partagée)
from .test_live_chances import _predict

Factory = async_sessionmaker[AsyncSession]


def test_windows_pause_60_75() -> None:
    w = live_coupons.window
    assert w("HT", 45) == ("mi-temps", 50)
    assert w("2H", 48) == ("mi-temps", 50)
    assert w("2H", 51) is None
    assert w("2H", 60) == ("60'", 63)
    assert w("2H", 64) is None
    assert w("2H", 78) == ("75'", 78)
    assert w("2H", 79) is None
    assert w("1H", 30) is None
    assert live_coupons.odds_wanted("2H", 59)
    assert not live_coupons.odds_wanted("2H", 55)


def test_live_odds_read_in_our_keys_suspended_left_out() -> None:
    entry = {
        "odds": [
            {"name": "Fulltime Result", "values": [
                {"value": "Home", "odd": "1.285", "suspended": False},
                {"value": "Draw", "odd": "5.5", "suspended": False},
                {"value": "Away", "odd": "11", "suspended": True}]},
            {"name": "Double Chance", "values": [{"value": "Home or Draw", "odd": "1.05"}]},
            {"name": "Match Goals", "values": [
                {"value": "Over", "handicap": "2.5", "odd": "1.8"},
                {"value": "Under", "handicap": "2.5", "odd": "1.909"},
                {"value": "Over", "handicap": "3", "odd": "2.6"}]},
            {"name": "Both Teams to Score", "values": [{"value": "Yes", "odd": "1.444"}]},
            {"name": "Race to the 7th corner?", "values": [{"value": "Home", "odd": "1.5"}]},
        ]
    }  # fmt: skip
    assert live_coupons.parse_live_odds(entry) == {
        "1X2||home": "1.285", "1X2||draw": "5.5", "DC||1X": "1.05",
        "OU|2.5|over": "1.8", "OU|2.5|under": "1.909", "BTTS||yes": "1.444",
    }  # fmt: skip


def test_odds_entry_kept_only_at_the_same_score_and_not_suspended() -> None:
    entry = {"teams": {"home": {"goals": 1}, "away": {"goals": 0}}, "status": {}}
    assert live_coupons.entry_current(entry, [1, 0])
    assert not live_coupons.entry_current(entry, [2, 0])  # cotes d'avant le but
    assert not live_coupons.entry_current(entry, None)
    assert not live_coupons.entry_current({**entry, "status": {"blocked": True}}, [1, 0])
    assert not live_coupons.entry_current({**entry, "status": {"stopped": True}}, [1, 0])


def test_pick_follows_the_profile_band_and_the_exclusions() -> None:
    markets = {"1X2||home": 0.84, "OU|2.5|under": 0.70, "OU|3.5|under": 0.86, "DC||1X": 0.95}
    odds = {k: "1.20" for k in markets}
    sure = live_coupons.pick(markets, odds, "Sûr", "mi-temps", premium=True)
    assert sure is not None
    assert sure[0] == "1X2||home"  # le plus proche de 83,5 %
    assert live_coupons.pick(markets, {}, "Sûr", "mi-temps", premium=True) is None  # pas de cote
    balanced = live_coupons.pick(markets, odds, "Équilibré", "mi-temps", premium=True)
    assert balanced is not None
    assert balanced[0] == "OU|2.5|under"
    # À la 75e, « plus ou moins de buts » n'est pas proposé en Équilibré (étude du 13/11).
    assert live_coupons.pick(markets, odds, "Équilibré", "75'", premium=True) is None


async def _live_world(db_factory: Factory, world: dict[str, Any]) -> tuple[int, int]:  # noqa: F811
    """m1 à la pause (1-0), m2 à la 61e (1-0) ; chances et coupon en direct publiés ; cotes
    en direct relevées à l'instant."""
    now = datetime.now(UTC)
    m1, m2 = world["m1"], world["m2"]
    async with db_factory() as session:
        day = await session.scalar(select(Match.match_date).where(Match.id == m1))
        assert day is not None
        await _predict(session, [m1, m2], day - timedelta(days=1))
        for mid, status, minute, score in ((m1, "HT", 45, (1, 0)), (m2, "2H", 61, (1, 0))):
            await session.execute(
                update(Match).where(Match.id == mid).values(
                    api_status=status, live_minute=minute, live_home_goals=score[0],
                    live_away_goals=score[1], home_goals_ht=score[0], away_goals_ht=score[1],
                    kickoff_at=now - timedelta(minutes=minute + 15),
                )
            )  # fmt: skip
            session.add(
                LiveSnapshot(
                    match_id=mid, taken_at=now - timedelta(seconds=30), status=status,
                    minute=minute, extra=0, home_goals=score[0], away_goals=score[1],
                )
            )  # fmt: skip
        await session.commit()
        await set_flag(session, LIVE_KEY, True)
        await live_coupons.set_settings(session, True, "indicative")
    redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    quotes = {
        "1X2||home": "1.20", "1X2||draw": "6.0", "1X2||away": "15", "DC||1X": "1.04",
        "OU|0.5|over": "1.30", "OU|1.5|over": "2.10", "OU|1.5|under": "1.70",
        "OU|2.5|over": "3.6", "OU|2.5|under": "1.25", "OU|3.5|under": "1.08",
    }  # fmt: skip
    await live_coupons.store_odds(
        redis,
        {
            m: {"at": now.isoformat(), "update": None, "odds": quotes, "state": [1, 0, 0]}
            for m in (m1, m2)
        },
    )
    await redis.aclose()
    return m1, m2


async def test_proposals_free_and_premium_then_live_bet(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    m1, m2 = await _live_world(db_factory, world)
    headers = await _login(client)

    # Sans Premium : Sûr complet (marchés gratuits), Équilibré et Audacieux sans sélection.
    data = (await client.get("/api/v1/live/coupons", headers=headers)).json()
    assert data["published"] is True
    assert data["odds_source"] == "indicative"
    assert {m["match_id"] for m in data["matches"]} == {m1, m2}
    by_id = {m["match_id"]: m for m in data["matches"]}
    assert (by_id[m1]["moment"], by_id[m1]["closes_at"]) == ("mi-temps", 50)
    assert (by_id[m2]["moment"], by_id[m2]["closes_at"]) == ("60'", 63)
    sure = data["combos"]["Sûr"]
    assert sure["locked"] is False
    assert sure["size"] == 2
    assert {s["match_id"] for s in sure["selections"]} == {m1, m2}  # une sélection par match
    assert all(s["market"] in ("1X2", "OU", "BTTS") for s in sure["selections"])
    probability = sure["selections"][0]["probability"] * sure["selections"][1]["probability"]
    assert abs(sure["probability"] - probability) < 1e-3
    for profile in ("Équilibré", "Audacieux"):
        if profile in data["combos"]:
            assert data["combos"][profile]["locked"] is True
            assert data["combos"][profile]["selections"] == []

    # Pari en direct sur le combiné Sûr : cote en direct, chance du moteur gardée.
    selections = [
        _sel(s["match_id"], s["market"], s["selection"], s["line"], odds=s["odds"])
        for s in sure["selections"]
    ]
    placed = await client.post(
        "/api/v1/bets", json={"stake": 1_000, "selections": selections}, headers=headers
    )
    assert placed.status_code == 201, placed.text
    async with db_factory() as session:
        sels = list(
            await session.scalars(
                select(BetSelection).where(BetSelection.bet_id == placed.json()["id"])
            )
        )
        assert {s.bookmaker for s in sels} == {"direct"}
        assert all(s.model_probability is not None for s in sels)
        bet = await session.get(Bet, placed.json()["id"])
        assert bet is not None
        assert bet.total_odds == Decimal(sure["odds"])

    # La cote a baissé depuis l'affichage : refusé, avec la nouvelle cote.
    s0 = sure["selections"][0]
    higher = _sel(s0["match_id"], s0["market"], s0["selection"], s0["line"], odds="9.99")
    lowered = await client.post(
        "/api/v1/bets", json={"stake": 1_000, "selections": [higher]}, headers=headers
    )
    assert lowered.status_code == 409
    assert lowered.json()["error"]["details"]["odds"] == s0["odds"]

    # Fenêtre fermée (62e → 64e) : paris fermés comme avant.
    async with db_factory() as session:
        await session.execute(update(Match).where(Match.id == m2).values(live_minute=64))
        await session.commit()
    s1 = next(s for s in sure["selections"] if s["match_id"] == m2)
    closed = await client.post(
        "/api/v1/bets",
        json={"stake": 1_000, "selections": [
            _sel(s1["match_id"], s1["market"], s1["selection"], s1["line"])]},
        headers=headers,
    )  # fmt: skip
    assert closed.status_code == 400
    assert "déjà commencé" in closed.json()["error"]["message"]

    # Non publié : rien.
    async with db_factory() as session:
        await live_coupons.set_settings(session, False, "indicative")
    hidden = (await client.get("/api/v1/live/coupons", headers=headers)).json()
    assert (hidden["published"], hidden["matches"], hidden["combos"]) == (False, [], {})


async def test_proposals_without_recent_odds_are_not_shown(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    m1, m2 = await _live_world(db_factory, world)
    redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    old = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    for mid in (m1, m2):
        await redis.set(live_coupons.ODDS_KEY.format(mid), json.dumps({"at": old, "odds": {}}))
    await redis.aclose()
    data = (await client.get("/api/v1/live/coupons")).json()
    assert (data["matches"], data["combos"]) == ([], {})


async def test_odds_read_before_a_goal_or_a_red_card_are_refused(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    """Relecture du 13/11/2026 : cotes relevées à 1-0, but à 2-0 → pari refusé, match plus
    proposé ; refusé aussi dans les 2 minutes après un but, et après un carton rouge."""
    _, m2 = await _live_world(db_factory, world)
    headers = await _login(client)
    sure = (await client.get("/api/v1/live/coupons", headers=headers)).json()["combos"]["Sûr"]
    s2 = next(s for s in sure["selections"] if s["match_id"] == m2)
    sel = _sel(s2["match_id"], s2["market"], s2["selection"], s2["line"], odds=s2["odds"])
    bet = {"stake": 1_000, "selections": [sel]}

    # But à la 62e : 2-0 ; la cote gardée a été relevée à 1-0.
    now = datetime.now(UTC)
    async with db_factory() as session:
        await session.execute(
            update(Match).where(Match.id == m2).values(live_minute=62, live_home_goals=2)
        )
        session.add(
            LiveSnapshot(match_id=m2, taken_at=now - timedelta(seconds=10), status="2H",
                         minute=62, extra=0, home_goals=2, away_goals=0)
        )  # fmt: skip
        await session.commit()
    refused = await client.post("/api/v1/bets", json=bet, headers=headers)
    assert refused.status_code == 400
    assert "après un but" in refused.json()["error"]["message"]
    data = (await client.get("/api/v1/live/coupons", headers=headers)).json()
    assert m2 not in {m["match_id"] for m in data["matches"]}

    # Nouvelle cote relevée à 2-0, mais but il y a moins de 2 minutes : toujours refusé.
    redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    text = await redis.get(live_coupons.ODDS_KEY.format(m2))
    assert text is not None
    fresh = {**json.loads(text), "at": now.isoformat(), "state": [2, 0, 0]}
    await live_coupons.store_odds(redis, {m2: fresh})
    assert (await client.post("/api/v1/bets", json=bet, headers=headers)).status_code == 400

    # Deux minutes plus tard : jouable à nouveau (relevés reculés de 3 minutes).
    async with db_factory() as session:
        await session.execute(
            update(LiveSnapshot)
            .where(LiveSnapshot.match_id == m2)
            .values(taken_at=LiveSnapshot.taken_at - timedelta(minutes=3))
        )
        await session.commit()
    ok = await client.post("/api/v1/bets", json=bet, headers=headers)
    assert ok.status_code == 201, ok.text

    # Carton rouge après le relevé : refusé.
    async with db_factory() as session:
        session.add(MatchEvent(match_id=m2, seq=1, minute=62, side="away", kind="Card",
                               detail="Red Card"))  # fmt: skip
        await session.commit()
    red = await client.post("/api/v1/bets", json=bet, headers=headers)
    assert red.status_code == 400
    await redis.aclose()
