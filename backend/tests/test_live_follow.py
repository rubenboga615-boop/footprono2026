"""Suivi en direct : score pendant le match, résultat et statistiques dès la fin."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.football.models import DataSource, Match, MatchStatus, MatchTeamStats
from footprono.ingestion import service
from footprono.ingestion.live import collect_injuries, follow_live, regulation_score
from footprono.ingestion.reference import COMPETITIONS
from footprono.ingestion.service import IngestionRequest, run_ingestion
from footprono.ingestion.sources import api_football

from .conftest import make_settings

FIXTURES = Path(__file__).parent / "fixtures"
Factory = async_sessionmaker[AsyncSession]
NOW = datetime(2025, 5, 25, 17, 0, tzinfo=UTC)
INJURY_DAY = ("39", "2025-05-25")


def _item(fid: int, status: str, elapsed: int, goals: tuple[int, int], ht: tuple[int, int] | None):
    return {
        "fixture": {
            "id": fid,
            "date": "2025-05-25T15:00:00+00:00",
            "status": {"short": status, "elapsed": elapsed},
            "referee": None,
        },
        "league": {"round": "Regular Season - 38"},
        "teams": {"home": {"id": 1, "name": "A"}, "away": {"id": 2, "name": "B"}},
        "goals": {"home": goals[0], "away": goals[1]},
        "score": {"halftime": {"home": ht[0], "away": ht[1]} if ht else None},
    }


def _transport(calls: list[str]) -> httpx.MockTransport:
    stats = [{"type": "Corner Kicks", "value": 6}, {"type": "Yellow Cards", "value": 2}]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        headers = {"x-ratelimit-requests-remaining": "7000", "x-ratelimit-remaining": "290"}
        if request.url.path == "/status":
            body: Any = {"response": {"requests": {"current": 1, "limit_day": 7500}}}
        elif request.url.path == "/fixtures":
            assert request.url.params["ids"] == "7000-7001"
            playing = _item(7000, "2H", 90, (1, 0), (1, 0))
            playing["fixture"]["status"]["extra"] = 4  # 90+4
            playing["lineups"] = [{"team": {"id": 1}, "formation": "4-3-3", "startXI": []}]
            body = {"response": [playing, _item(7001, "FT", 90, (9, 9), (4, 4))]}
        elif request.url.path == "/injuries":
            body = {
                "response": [
                    {"player": {"name": "X", "type": "Missing Fixture", "reason": "Knee"},
                     "team": {"id": 1}, "fixture": {"id": fid}}
                    for fid in (7000, 424242)
                ]
                if (request.url.params["league"], request.url.params["date"]) == INJURY_DAY
                else []
            }  # fmt: skip
        else:
            assert request.url.params["fixture"] == "7001"
            body = {
                "response": [
                    {"team": {"id": t}, "statistics": stats, "statistics_1h": stats,
                     "statistics_2h": stats}
                    for t in (1, 2)
                ]
            }  # fmt: skip
        return httpx.Response(200, json={**body, "errors": []}, headers=headers)

    return httpx.MockTransport(handler)


_original_init = api_football.ApiFootballClient.__init__


def _fast_init(self: api_football.ApiFootballClient, key: str, **kwargs: Any) -> None:
    _original_init(self, key, **{**kwargs, "pause_seconds": 0})


async def test_follow_live_updates_score_then_finishes(
    db_factory: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, client: AsyncClient
) -> None:
    fd = IngestionRequest(DataSource.FOOTBALL_DATA, ["EPL"], [2024], FIXTURES / "football-data")
    await run_ingestion(db_factory, make_settings(raw_data_dir=tmp_path / "raw"), [fd])
    calls: list[str] = []
    monkeypatch.setattr(service, "api_football_transport", _transport(calls))
    monkeypatch.setattr(api_football.ApiFootballClient, "__init__", _fast_init)
    settings = make_settings(raw_data_dir=tmp_path / "raw", api_football_key="k" * 32)

    # Aucun match dans la fenêtre : aucune requête.
    async with db_factory() as session:
        idle = await follow_live(session, settings, now=NOW)
    assert idle == {"status": "idle", "requests": 0}
    assert calls == []

    async with db_factory() as session:
        last_day = await session.scalar(select(func.max(Match.match_date)))
        ids = list(
            await session.scalars(
                select(Match.id).where(Match.match_date == last_day).order_by(Match.id).limit(2)
            )
        )
        for n, match_id in enumerate(ids):
            await session.execute(
                update(Match)
                .where(Match.id == match_id)
                .values(
                    status=MatchStatus.SCHEDULED,
                    home_goals=None,
                    away_goals=None,
                    result_source=None,
                    api_football_id=7000 + n,
                    kickoff_at=NOW - timedelta(minutes=110),
                )
            )
        await session.commit()

    async with db_factory() as session:
        report = await follow_live(session, settings, now=NOW)
    assert report["status"] == "ok", report
    assert report["live"] == 1
    assert report["finished"] == ["A-B 9-9"]
    assert report["stats"] == 1
    assert calls[1:] == ["/fixtures", "/fixtures/statistics"]

    async with db_factory() as session:
        playing = await session.get(Match, ids[0])
        done = await session.get(Match, ids[1])
        n_stats = await session.scalar(
            select(func.count())
            .select_from(MatchTeamStats)
            .where(MatchTeamStats.match_id == ids[1])
        )
    assert playing is not None
    assert done is not None
    assert (playing.status, playing.api_status, playing.live_minute, playing.live_extra) == (
        MatchStatus.SCHEDULED, "2H", 90, 4,
    )  # fmt: skip
    assert (playing.live_home_goals, playing.live_away_goals) == (1, 0)
    # Coup d'envoi d'API-Football repris à chaque passage (15 h 00, pas 15 h 10 en base).
    assert playing.kickoff_at == datetime(2025, 5, 25, 15, 0, tzinfo=UTC)
    assert (done.status, done.home_goals, done.away_goals) == (MatchStatus.FINISHED, 9, 9)
    assert (done.home_goals_ht, done.result_source) == (4, "api_football")
    assert n_stats == 6  # 2 équipes x 3 périodes

    live = await client.get("/api/v1/live")
    assert [m["id"] for m in live.json()] == [ids[0]]
    assert (live.json()[0]["live_minute"], live.json()[0]["live_extra"]) == (90, 4)

    # Compositions : incluses dans la réponse du direct, aucune requête de plus.
    assert report["lineups"] == 1
    async with db_factory() as session:
        injuries = await collect_injuries(session, settings, today=NOW)
    assert injuries["status"] == "ok"
    assert injuries["requests"] == 2 * len(COMPETITIONS)  # (aujourd'hui, demain) par championnat
    assert (injuries["matches"], injuries["unknown_fixtures"]) == (1, 1)
    sheets = (await client.get(f"/api/v1/matches/{ids[0]}/team-sheets")).json()
    assert sheets["lineups"]["data"][0]["formation"] == "4-3-3"
    assert sheets["injuries"]["data"][0]["player"]["reason"] == "Knee"

    # Le lendemain, football-data confirme : le score provisoire différent est signalé
    # et remplacé ; le match joué n'est jamais remis « à venir ».
    report = await run_ingestion(db_factory, make_settings(raw_data_dir=tmp_path / "raw"), [fd])
    corrected = [i for i in report["files"][0]["issues"] if "score provisoire" in i]
    assert len(corrected) == 1
    async with db_factory() as session:
        done = await session.get(Match, ids[1])
    assert done is not None
    assert done.result_source == "football_data"
    assert (done.home_goals, done.away_goals) != (9, 9)


def test_regulation_score_ignores_extra_time() -> None:
    """Coupe : 1-1 après 90 minutes, 2-1 après prolongation ; le pari se règle sur 1-1."""
    item = _item(1, "AET", 120, (2, 1), (0, 0))
    item["score"]["fulltime"] = {"home": 1, "away": 1}
    assert regulation_score(item) == (1, 1)
    pens = _item(2, "PEN", 120, (1, 1), (0, 0))
    pens["score"]["fulltime"] = {"home": 1, "away": 1}
    assert regulation_score(pens) == (1, 1)
    assert regulation_score(_item(3, "FT", 90, (3, 0), (1, 0))) == (3, 0)


async def test_follow_live_every_minute_only_when_quota_allows(
    db_factory: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retour du fondateur du 12/11/2026 : relevé chaque minute ; les minutes impaires sont
    sautées quand le quota du jour baisse (retour à toutes les 2 minutes)."""
    from footprono.ingestion.live import EVERY_MINUTE_MARGIN

    fd = IngestionRequest(DataSource.FOOTBALL_DATA, ["EPL"], [2024], FIXTURES / "football-data")
    await run_ingestion(db_factory, make_settings(raw_data_dir=tmp_path / "raw"), [fd])
    used = {"current": 1}
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/status":
            body: Any = {"response": {"requests": {**used, "limit_day": 7500}}}
        else:
            body = {"response": [_item(7000, "1H", 20, (0, 0), None)]}
        return httpx.Response(200, json={**body, "errors": []})

    monkeypatch.setattr(service, "api_football_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(api_football.ApiFootballClient, "__init__", _fast_init)
    settings = make_settings(raw_data_dir=tmp_path / "raw", api_football_key="k" * 32)
    async with db_factory() as session:
        last_day = await session.scalar(select(func.max(Match.match_date)))
        mid = await session.scalar(select(Match.id).where(Match.match_date == last_day).limit(1))
        await session.execute(
            update(Match).where(Match.id == mid).values(
                status=MatchStatus.SCHEDULED, home_goals=None, away_goals=None,
                result_source=None, api_football_id=7000, kickoff_at=NOW - timedelta(minutes=20),
            )
        )  # fmt: skip
        await session.commit()

    odd = NOW + timedelta(minutes=1)
    async with db_factory() as session:
        assert (await follow_live(session, settings, now=odd))["live"] == 1
    assert calls == ["/status", "/fixtures"]

    calls.clear()
    used["current"] = 7500 - settings.api_football_min_remaining - EVERY_MINUTE_MARGIN + 1
    async with db_factory() as session:
        skipped = await follow_live(session, settings, now=odd)
    assert skipped["requests"] == 0
    assert calls == ["/status"]  # /status ne compte pas dans le quota

    calls.clear()
    async with db_factory() as session:
        assert (await follow_live(session, settings, now=NOW + timedelta(minutes=2)))["live"] == 1
    assert calls == ["/status", "/fixtures"]


async def test_follow_live_task_runs_one_pass_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Passage chaque minute : un passage encore en cours fait sauter le suivant."""
    from redis.asyncio import Redis

    from footprono.worker import tasks

    from .conftest import TEST_REDIS_URL

    monkeypatch.setattr(tasks, "get_settings", make_settings)
    ran: list[int] = []

    async def once(_settings: Any) -> dict[str, Any]:
        ran.append(1)
        return {"status": "ok"}

    monkeypatch.setattr(tasks, "_follow_live_once", once)
    r = Redis.from_url(TEST_REDIS_URL)
    await r.delete(tasks.FOLLOW_LOCK)
    await r.set(tasks.FOLLOW_LOCK, "1")
    assert (await tasks._follow_live())["skipped"] == "passage précédent en cours"
    await r.delete(tasks.FOLLOW_LOCK)
    assert await tasks._follow_live() == {"status": "ok"}
    assert ran == [1]
    assert await r.get(tasks.FOLLOW_LOCK) is None  # verrou rendu
    await r.aclose()


async def test_follow_live_reads_live_odds_only_in_a_window_when_published(
    db_factory: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coupon en direct (13/11/2026) : /odds/live une fois par passage, seulement si un match
    suivi est dans une fenêtre (ici la 61e) et que le coupon en direct est publié."""
    from footprono.bookmaker import live_coupons

    fd = IngestionRequest(DataSource.FOOTBALL_DATA, ["EPL"], [2024], FIXTURES / "football-data")
    await run_ingestion(db_factory, make_settings(raw_data_dir=tmp_path / "raw"), [fd])
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/status":
            body: Any = {"response": {"requests": {"current": 1, "limit_day": 7500}}}
        elif request.url.path == "/odds/live":
            body = {"response": [
                {"fixture": {"id": 7000}, "update": "2026-11-13T13:20:00+00:00",
                 "teams": {"home": {"goals": 1}, "away": {"goals": 0}}, "odds": [
                    {"name": "Fulltime Result", "values": [{"value": "Home", "odd": "1.5"}]}]},
                {"fixture": {"id": 9999}, "odds": []},
            ]}  # fmt: skip
        else:
            body = {"response": [_item(7000, "2H", 61, (1, 0), (1, 0))]}
        return httpx.Response(200, json={**body, "errors": []})

    monkeypatch.setattr(service, "api_football_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(api_football.ApiFootballClient, "__init__", _fast_init)
    settings = make_settings(raw_data_dir=tmp_path / "raw", api_football_key="k" * 32)
    async with db_factory() as session:
        last_day = await session.scalar(select(func.max(Match.match_date)))
        mid = await session.scalar(select(Match.id).where(Match.match_date == last_day).limit(1))
        await session.execute(
            update(Match).where(Match.id == mid).values(
                status=MatchStatus.SCHEDULED, home_goals=None, away_goals=None,
                result_source=None, api_football_id=7000, kickoff_at=NOW - timedelta(minutes=75),
            )
        )  # fmt: skip
        await session.commit()

    even = NOW + timedelta(minutes=2)
    async with db_factory() as session:
        report = await follow_live(session, settings, now=even)
    assert "/odds/live" not in calls  # pas publié : aucune requête de plus
    assert "live_odds" not in report

    async with db_factory() as session:
        await live_coupons.set_settings(session, True, "indicative")
    calls.clear()
    async with db_factory() as session:
        report = await follow_live(session, settings, now=even)
    assert calls.count("/odds/live") == 1
    assert report["live_odds"] == {
        mid: {"at": even.isoformat(), "update": "2026-11-13T13:20:00+00:00",
              "odds": {"1X2||home": "1.5"}}
    }  # fmt: skip
