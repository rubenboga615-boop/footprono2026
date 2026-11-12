"""Chances en direct (plan du 10/11/2026, étape 6) : vérification sur les matchs joués,
calcul pendant le match, publication refusée tant que la vérification n'est pas juste."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.engine.live import LiveModel
from footprono.football.models import LiveSnapshot, Match, MatchEvent, MatchStatus
from footprono.predictions import live_chances
from footprono.predictions.models import MatchPrediction, PredictionRun
from footprono.predictions.publication import LIVE_KEY, live_published, set_flag

from .test_live_details import _two_matches

Factory = async_sessionmaker[AsyncSession]
NOW = datetime(2026, 11, 10, 20, 0, tzinfo=UTC)


async def _predict(session: AsyncSession, match_ids: list[int], as_of: date) -> None:
    run = PredictionRun(engine_version="test", as_of=as_of, status="ok")
    session.add(run)
    await session.flush()
    for mid in match_ids:
        session.add(
            MatchPrediction(
                run_id=run.id, match_id=mid, lambda_home=1.6, lambda_away=1.1, rho=0.0,
                share_home=0.45, share_away=0.44, markets={}, counts={}, context={},
            )
        )  # fmt: skip


def _event(mid: int, seq: int, minute: int, side: str, kind: str, detail: str) -> MatchEvent:
    return MatchEvent(
        match_id=mid, seq=seq, minute=minute, extra=None, side=side, kind=kind, detail=detail
    )


async def test_study_of_played_matches(
    db_factory: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Paquets d'un seul match : la console demandait 50 000 numéros d'un coup (limite de
    # PostgreSQL : 32 767 paramètres par requête).
    monkeypatch.setattr(live_chances, "CHUNK", 1)
    ids = await _two_matches(db_factory, tmp_path)
    async with db_factory() as session:
        day = await session.scalar(select(Match.match_date).where(Match.id == ids[0]))
        assert day is not None
        await _predict(session, ids, day - timedelta(days=1))
        # 1er match : 2-1 (pause 1-0), but contre son camp compté pour l'adversaire chez
        # API-Football ; 2e match : score des événements faux, écarté.
        await session.execute(
            update(Match).where(Match.id == ids[0]).values(
                home_goals=2, away_goals=1, home_goals_ht=1, away_goals_ht=0,
                status=MatchStatus.FINISHED,
            )
        )  # fmt: skip
        await session.execute(
            update(Match).where(Match.id == ids[1]).values(
                home_goals=0, away_goals=0, home_goals_ht=0, away_goals_ht=0,
                status=MatchStatus.FINISHED,
            )
        )  # fmt: skip
        session.add_all([
            _event(ids[0], 0, 20, "home", "Goal", "Normal Goal"),
            _event(ids[0], 1, 55, "away", "Goal", "Own Goal"),  # marqué par l'extérieur…
            _event(ids[0], 2, 80, "away", "Goal", "Normal Goal"),
            _event(ids[0], 3, 85, "home", "Goal", "Missed Penalty"),
            _event(ids[1], 0, 10, "home", "Goal", "Normal Goal"),
        ])  # fmt: skip
        for mid in ids:
            session.add(
                LiveSnapshot(match_id=mid, taken_at=NOW, status="FT", minute=90, extra=0,
                             home_goals=0, away_goals=0)
            )  # fmt: skip
        await session.commit()

        rep = await live_chances.study(session)
        # Saisons passées : prévisions rejouées données à la main, même résultat.
        past, matches = await live_chances.history_study(
            session, [(i, (1.6, 1.1, 0.45, 0.44)) for i in ids]
        )
    assert (past["matches"], past["inconsistent"]) == (1, 1)
    # Buts à 20', 55' et 80' : 1 sur 1 en 1re période (15-30), 2 en 2e (45-60, 75-90+).
    assert past["goal_minutes"]["15-30"] == 1.0
    assert past["goal_minutes"]["45-60"] == 0.5
    assert len(matches) == 1
    # Convention « contre son camp » inversée : 2 buts pour le domicile, 1 pour l'extérieur.
    assert rep["matches"] == 1
    assert rep["inconsistent"] == 1
    checkpoints = {r["checkpoint"] for r in rep["rows"]}
    assert checkpoints == {"15'", "30'", "mi-temps", "60'", "75'"}
    assert all(r["verdict"] == "trop peu" for r in rep["rows"])


async def test_current_chances_and_publication(
    db_factory: Factory, tmp_path: Path, client: httpx.AsyncClient
) -> None:
    ids = await _two_matches(db_factory, tmp_path)
    async with db_factory() as session:
        day = await session.scalar(select(Match.match_date).where(Match.id == ids[0]))
        assert day is not None
        await _predict(session, ids, day - timedelta(days=1))
        session.add_all([
            LiveSnapshot(match_id=ids[0], taken_at=NOW, status="2H", minute=70, extra=0,
                         home_goals=1, away_goals=0),
            LiveSnapshot(match_id=ids[1], taken_at=NOW, status="2H", minute=70, extra=0,
                         home_goals=0, away_goals=0),
            _event(ids[1], 0, 50, "away", "Card", "Red Card"),
        ])  # fmt: skip
        await session.execute(
            update(Match).where(Match.id == ids[0]).values(home_goals_ht=1, away_goals_ht=0)
        )
        await session.commit()

        found = await live_chances.current(session, ids)
        # Carton rouge : pas de chance calculée pour le 2e match.
        assert set(found) == {ids[0]}
        chances = found[ids[0]]["markets"]
        assert chances["OU|0.5|over"] == 1.0
        assert chances["1X2||home"] > 0.7
        assert await live_published(session) is False
        # Marché faux à la vérification : pas de chiffre dans sa période (11/11/2026).
        await live_chances.save_model(
            session, LiveModel(), {"learned_at": "11/11/2026", "train": "2021-2024",
                                   "test": "2025", "validated": True,
                                   "excluded": {"first": [], "second": ["Les deux marquent"]}},
        )  # fmt: skip
        again = (await live_chances.current(session, ids))[ids[0]]["markets"]
        assert "BTTS||yes" not in again
        assert "1X2||home" in again

    params = {"match_ids": [str(i) for i in ids]}
    hidden = (await client.get("/api/v1/live/chances", params=params)).json()
    assert hidden == {"published": False, "matches": {}}

    async with db_factory() as session:
        await set_flag(session, LIVE_KEY, True)
    shown = (await client.get("/api/v1/live/chances", params=params)).json()
    assert shown["published"] is True
    assert list(shown["matches"]) == [str(ids[0])]
    assert shown["matches"][str(ids[0])]["minute"] == 70


def test_publication_only_when_every_checkpoint_is_right() -> None:
    from footprono.console.actions import _live_verdict

    def row(checkpoint: str, verdict: str) -> dict[str, str]:
        return {"checkpoint": checkpoint, "family": "Résultat (1X2)", "verdict": verdict}

    good = {"rows": [row(c, "juste") for c in ("15'", "30'", "mi-temps", "60'", "75'")]}
    assert _live_verdict(good)[0] is True
    bad = {"rows": [*good["rows"][:4], row("75'", "à revoir")]}
    ok, lines = _live_verdict(bad)
    assert ok is False
    assert lines[-1] == "75' : 1 marchés vérifiés, à revoir : Résultat (1X2)"
    assert _live_verdict({"rows": good["rows"][:4]})[0] is False  # 75' : trop peu


def test_backfill_offers_cups_and_national_teams() -> None:
    from footprono.console.registry import get_action

    param = next(p for p in get_action("details_backfill").params if p.name == "competition")
    codes = [code for code, _ in param.choices()]
    assert codes[0] == ""  # Tous : championnats, coupes et sélections
    assert {"EPL", "ISR", "UCL", "UEL", "UECL", "UNL", "WCQ_EUR", "CAN"} <= set(codes)


async def test_live_tab_timeline_stats_by_half_and_lineups(
    db_factory: Factory, tmp_path: Path, client: httpx.AsyncClient
) -> None:
    from footprono.football.live_view import second_half
    from footprono.football.models import MatchLineup, MatchLineupPlayer

    ids = await _two_matches(db_factory, tmp_path)
    mid = ids[0]
    half = {"Shots on Goal": 2, "Ball Possession": "60%", "expected_goals": "0.71", "Fouls": None}
    now = {"Shots on Goal": 5, "Ball Possession": "55%", "expected_goals": "1.62", "Fouls": 7}
    async with db_factory() as session:
        session.add_all([
            LiveSnapshot(match_id=mid, taken_at=NOW - timedelta(minutes=30), status="HT",
                         minute=45, extra=0, home_goals=1, away_goals=0,
                         home_stats=half, away_stats=half),
            LiveSnapshot(match_id=mid, taken_at=NOW, status="2H", minute=63, extra=0,
                         home_goals=2, away_goals=1, home_stats=now, away_stats=now),
            _event(mid, 0, 23, "home", "Goal", "Normal Goal"),
            _event(mid, 1, 46, "away", "subst", "Substitution 1"),
            MatchLineup(match_id=mid, side="home", formation="4-3-3", coach="Farke"),
            MatchLineupPlayer(match_id=mid, side="home", starter=True, name="Meslier",
                              number=1, position="G", grid="1:1"),
            MatchLineupPlayer(match_id=mid, side="home", starter=False, name="Piroe",
                              number=19, position="F", grid=None),
        ])  # fmt: skip
        await session.commit()

    body = (await client.get(f"/api/v1/matches/{mid}/live")).json()
    assert (body["status"], body["minute"]) == ("2H", 63)
    assert [e["minute"] for e in body["events"]] == [23, 46]
    stats = body["stats"]
    assert stats["match"]["home"]["Shots on Goal"] == 5
    assert stats["first"]["home"]["Shots on Goal"] == 2
    # 2e mi-temps : différence, sans les pourcentages.
    assert stats["second"]["home"] == {"Shots on Goal": 3, "expected_goals": 0.91, "Fouls": 7}
    (home,) = body["lineups"]
    assert (home["formation"], home["coach"]) == ("4-3-3", "Farke")
    assert [p["starter"] for p in home["players"]] == [True, False]
    assert second_half(now, None) is None

    summary = (await client.get("/api/v1/live/summary", params={"match_ids": [mid]})).json()
    assert summary[str(mid)]["goals"] == [
        {"minute": 23, "extra": None, "side": "home", "player": None, "own_goal": False}
    ]
    assert summary[str(mid)]["reds"] == []

    missing = await client.get("/api/v1/matches/999999/live")
    assert missing.status_code == 404


async def test_live_model_kept_only_after_validation(db_factory: Factory) -> None:
    from footprono.engine.live import DEFAULT_MODEL, LiveModel

    async with db_factory() as session:
        model, info = await live_chances.stored_model(session)
        assert (model, info) == (DEFAULT_MODEL, None)
        learned = LiveModel(first=(1.1,) * 10, second=(0.9,) * 10, effect=(1.0, 1.2, 1.0, 0.9, 1.0))
        await live_chances.save_model(
            session, learned, {"learned_at": "11/11/2026", "train": "2021-2024", "test": "2025",
                               "validated": True},
        )  # fmt: skip
        model, info = await live_chances.stored_model(session)
    assert model == learned
    assert info is not None
    assert info["test"] == "2025"


def test_decision_core_market_everywhere_others_withdrawn_by_period() -> None:
    from footprono.console.actions import _live_decision

    def row(checkpoint: str, family: str, verdict: str) -> dict[str, str]:
        return {"checkpoint": checkpoint, "family": family, "verdict": verdict}

    points = ("15'", "30'", "mi-temps", "60'", "75'")
    rows = [row(c, "Résultat (1X2)", "juste") for c in points]
    rows += [
        row("60'", "Les deux marquent", "à revoir"),
        row("15'", "Buts d'une équipe", "à revoir"),
    ]
    ok, lines, excluded = _live_decision({"rows": rows})
    assert ok is True
    assert excluded == {"first": ["Buts d'une équipe"], "second": ["Les deux marquent"]}
    assert lines[3] == "60' : 2 marchés vérifiés, faux : Les deux marquent"
    rows[3] = row("60'", "Résultat (1X2)", "à revoir")
    assert _live_decision({"rows": rows})[0] is False  # le résultat du match doit être juste


def test_rule_three_points_or_chance() -> None:
    from footprono.engine.live_study import Entry, report

    # 400 sélections annoncées à 25 %, arrivées à 28,5 % : 3,5 points, mais dans deux
    # erreurs types (4,3 points) : juste. À 31 % : 6 points, faux.
    def entries(won: int) -> list[Entry]:
        return [Entry("60'", "Les deux marquent", 0.25, i < won) for i in range(400)]

    assert report(entries(114))["rows"][0]["verdict"] == "juste"
    assert report(entries(124))["rows"][0]["verdict"] == "à revoir"


async def test_live_feed_message_and_publication(
    db_factory: Factory, tmp_path: Path, client: httpx.AsyncClient
) -> None:
    """Retour du fondateur du 12/11/2026 : chaque relevé part aussitôt vers l'application
    ouverte (score, minute, buts, chances publiées), sans requête de plus."""
    import json

    from redis.asyncio import Redis

    from footprono.notifications import live_feed

    from .conftest import TEST_REDIS_URL

    ids = await _two_matches(db_factory, tmp_path)
    async with db_factory() as session:
        day = await session.scalar(select(Match.match_date).where(Match.id == ids[0]))
        assert day is not None
        await _predict(session, ids, day - timedelta(days=1))
        await session.execute(
            update(Match).where(Match.id == ids[0]).values(
                status=MatchStatus.SCHEDULED, api_status="2H", live_minute=70, live_extra=0,
                live_home_goals=1, live_away_goals=0, home_goals=None, away_goals=None,
                home_goals_ht=1, away_goals_ht=0,
            )
        )  # fmt: skip
        session.add_all([
            LiveSnapshot(match_id=ids[0], taken_at=NOW, status="2H", minute=70, extra=0,
                         home_goals=1, away_goals=0),
            _event(ids[0], 0, 12, "home", "Goal", "Normal Goal"),
        ])  # fmt: skip
        await session.commit()

        hidden = await live_feed.live_message(session, [ids[0]])
        (m,) = hidden["matches"]
        assert (m["id"], m["minute"], m["home"], m["away"]) == (ids[0], 70, 1, 0)
        assert (m["status"], m["api_status"]) == ("scheduled", "2H")
        assert [g["minute"] for g in m["goals"]] == [12]
        assert m["chances"] == {}  # chances en direct pas encore publiées

        await set_flag(session, LIVE_KEY, True)
        shown = (await live_feed.live_message(session, [ids[0]]))["matches"][0]["chances"]
        assert set(shown) <= set(live_feed.SHOWN)
        assert shown["1X2||home"] > 0.7

        redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
        pubsub = redis.pubsub()
        await pubsub.subscribe(live_feed.LIVE_CHANNEL)
        await pubsub.get_message(timeout=1)  # confirmation de l'abonnement
        assert await live_feed.publish_live(redis, session, []) == 0
        assert await live_feed.publish_live(redis, session, [ids[0], ids[0]]) == 1
        got = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
        await pubsub.aclose()
        await redis.aclose()
    assert got is not None
    data = json.loads(got["data"])
    assert (data["type"], data["matches"][0]["id"]) == ("live", ids[0])
    assert "kickoff_at" in data["matches"][0]
    # Sans WebSocket (invité) : le même relevé, relu sans toucher à la base.
    again = (await client.get("/api/v1/live/feed")).json()
    assert again == data
