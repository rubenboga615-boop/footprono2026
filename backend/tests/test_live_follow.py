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
from footprono.ingestion.live import collect_injuries, follow_live
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
            playing = _item(7000, "2H", 67, (1, 0), (1, 0))
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
    assert (playing.status, playing.api_status, playing.live_minute) == (
        MatchStatus.SCHEDULED, "2H", 67,
    )  # fmt: skip
    assert (playing.live_home_goals, playing.live_away_goals) == (1, 0)
    assert (done.status, done.home_goals, done.away_goals) == (MatchStatus.FINISHED, 9, 9)
    assert (done.home_goals_ht, done.result_source) == (4, "api_football")
    assert n_stats == 6  # 2 équipes x 3 périodes

    live = await client.get("/api/v1/live")
    assert [m["id"] for m in live.json()] == [ids[0]]
    assert live.json()[0]["live_minute"] == 67

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
