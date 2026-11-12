"""Données du direct (plan du 10/11/2026, étape 1) : événements, relevés, compositions et
joueurs rangés à chaque passage ; score de la mi-temps dès la pause ; relecture des
relevés gardés ; rattrapage des matchs passés ; essai « Tester le direct »."""

from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.football.models import (
    DataSource,
    LiveSnapshot,
    Match,
    MatchEvent,
    MatchLineup,
    MatchLineupPlayer,
    MatchStatus,
    PlayerMatchStats,
)
from footprono.ingestion import service
from footprono.ingestion.live import backfill_details, follow_live, probe_live, replay_live_files
from footprono.ingestion.service import IngestionRequest, run_ingestion
from footprono.ingestion.sources import api_football

from .conftest import make_settings
from .test_live_follow import FIXTURES, NOW, _fast_init, _item

Factory = async_sessionmaker[AsyncSession]

STATS = [
    {"type": "Shots on Goal", "value": 4},
    {"type": "Corner Kicks", "value": 5},
    {"type": "Ball Possession", "value": "58%"},
    {"type": "expected_goals", "value": "1.21"},
]


def _rich(fid: int, status: str, elapsed: int, goals: tuple[int, int], var: bool = False) -> Any:
    item = _item(fid, status, elapsed, goals, (1, 0) if status != "1H" else None)
    events = [
        {"time": {"elapsed": 23, "extra": None}, "team": {"id": 1},
         "player": {"id": 10, "name": "Buteur"}, "assist": {"id": 11, "name": "Passeur"},
         "type": "Goal", "detail": "Normal Goal", "comments": None},
        {"time": {"elapsed": 45, "extra": 2}, "team": {"id": 2},
         "player": {"id": 20, "name": "Défenseur"}, "assist": {"id": None, "name": None},
         "type": "Card", "detail": "Yellow Card", "comments": "Foul"},
    ]  # fmt: skip
    if not var:
        events.append(
            {"time": {"elapsed": 60, "extra": None}, "team": {"id": 1},
             "player": {"id": 10, "name": "Buteur"}, "assist": {},
             "type": "Goal", "detail": "Normal Goal", "comments": None}
        )  # fmt: skip
    item["events"] = events
    item["statistics"] = [{"team": {"id": t}, "statistics": STATS} for t in (1, 2)]
    item["lineups"] = [
        {"team": {"id": t}, "formation": "4-3-3", "coach": {"id": 90 + t, "name": f"Coach {t}"},
         "startXI": [{"player": {"id": 10 * t, "name": f"Titulaire {t}", "number": 9,
                                 "pos": "F", "grid": "4:1"}}],
         "substitutes": [{"player": {"id": 10 * t + 5, "name": f"Remplaçant {t}",
                                     "number": 14, "pos": "M", "grid": None}}]}
        for t in (2, 1)
    ]  # fmt: skip
    item["players"] = [
        {"team": {"id": 1}, "players": [
            {"player": {"id": 10, "name": "Buteur"}, "statistics": [
                {"games": {"minutes": elapsed, "rating": "8.1"},
                 "goals": {"total": 1, "assists": None},
                 "shots": {"total": 3, "on": 2}, "cards": {"yellow": 0, "red": 0}}]}]},
    ]  # fmt: skip
    return item


def _transport(calls: list[str], answer: dict[str, Any]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.url.path}?{request.url.query.decode()}")
        headers = {"x-ratelimit-requests-remaining": "7000", "x-ratelimit-remaining": "290"}
        if request.url.path == "/status":
            body: Any = {"response": {"requests": {"current": 1, "limit_day": 7500}}}
        elif request.url.path == "/odds/live":
            body = {"response": [{
                "fixture": {"id": 8000, "status": {"long": "Halftime", "elapsed": 45,
                                                   "seconds": "45:00"}},
                "status": {"stopped": False, "blocked": False, "finished": False},
                "update": "2026-11-12T16:55:04+00:00",
                "source": "exemple",
                "odds": [
                    {"id": 59, "name": "Fulltime Result", "values": [
                        {"value": "Home", "odd": "1.45", "handicap": None, "main": None,
                         "suspended": False},
                        {"value": "Draw", "odd": "3.90", "handicap": None, "main": None,
                         "suspended": False},
                        {"value": "Away", "odd": "9.00", "handicap": None, "main": None,
                         "suspended": True}]},
                    {"id": 36, "name": "Over/Under Line", "values": [
                        {"value": "Over", "odd": "1.80", "handicap": "2.5", "main": True,
                         "suspended": False},
                        {"value": "Under", "odd": "1.95", "handicap": "2.5", "main": True,
                         "suspended": False},
                        {"value": "Over", "odd": "3.10", "handicap": "3.5", "main": False,
                         "suspended": False}]},
                ],
            }]}  # fmt: skip
        else:
            ids = request.url.params["ids"].split("-")
            body = {"response": [answer[i] for i in ids if i in answer]}
        return httpx.Response(200, json={**body, "errors": []}, headers=headers)

    return httpx.MockTransport(handler)


async def _two_matches(db_factory: Factory, tmp_path: Path) -> list[int]:
    fd = IngestionRequest(DataSource.FOOTBALL_DATA, ["EPL"], [2024], FIXTURES / "football-data")
    await run_ingestion(db_factory, make_settings(raw_data_dir=tmp_path / "raw"), [fd])
    async with db_factory() as session:
        last_day = await session.scalar(select(func.max(Match.match_date)))
        return list(
            await session.scalars(
                select(Match.id).where(Match.match_date == last_day).order_by(Match.id).limit(2)
            )
        )


async def _count(session: AsyncSession, model: Any, match_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(model).where(model.match_id == match_id)
        )
        or 0
    )


async def test_live_details_stored_each_pass_and_half_time_score(
    db_factory: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = await _two_matches(db_factory, tmp_path)
    async with db_factory() as session:
        await session.execute(
            update(Match)
            .where(Match.id == ids[0])
            .values(
                status=MatchStatus.SCHEDULED, home_goals=None, away_goals=None,
                home_goals_ht=None, away_goals_ht=None, result_source=None,
                api_football_id=7000, kickoff_at=NOW - timedelta(minutes=70),
            )
        )  # fmt: skip
        await session.commit()
    monkeypatch.setattr(api_football.ApiFootballClient, "__init__", _fast_init)
    settings = make_settings(raw_data_dir=tmp_path / "raw", api_football_key="k" * 32)
    calls: list[str] = []

    # 2e mi-temps, 60e minute, 2-0 : score de la mi-temps enregistré sans attendre la fin.
    answer = {"7000": _rich(7000, "2H", 60, (2, 0))}
    monkeypatch.setattr(service, "api_football_transport", _transport(calls, answer))
    async with db_factory() as session:
        report = await follow_live(session, settings, now=NOW)
    assert report["status"] == "ok", report
    assert (report["events"], report["snapshots"]) == (3, 1)
    assert [c.split("?")[0] for c in calls] == ["/status", "/fixtures"]  # aucune requête en plus
    async with db_factory() as session:
        match = await session.get(Match, ids[0])
        assert match is not None
        assert match.status is MatchStatus.SCHEDULED  # toujours en cours
        assert (match.home_goals_ht, match.away_goals_ht) == (1, 0)
        events = (
            await session.scalars(
                select(MatchEvent).where(MatchEvent.match_id == ids[0]).order_by(MatchEvent.seq)
            )
        ).all()
        assert [(e.minute, e.extra, e.side, e.kind, e.player) for e in events] == [
            (23, None, "home", "Goal", "Buteur"),
            (45, 2, "away", "Card", "Défenseur"),
            (60, None, "home", "Goal", "Buteur"),
        ]
        assert events[0].assist == "Passeur"
        snap = await session.scalar(select(LiveSnapshot).where(LiveSnapshot.match_id == ids[0]))
        assert snap is not None
        assert (snap.status, snap.minute, snap.home_goals, snap.away_goals) == ("2H", 60, 2, 0)
        # Toutes les statistiques, telles que données (même celles pas encore affichées).
        assert snap.home_stats == {s["type"]: s["value"] for s in STATS}
        lineups = (
            await session.scalars(select(MatchLineup).where(MatchLineup.match_id == ids[0]))
        ).all()
        assert sorted((lu.side, lu.formation, lu.coach) for lu in lineups) == [
            ("away", "4-3-3", "Coach 2"),
            ("home", "4-3-3", "Coach 1"),
        ]
        players = (
            await session.scalars(
                select(MatchLineupPlayer).where(MatchLineupPlayer.match_id == ids[0])
            )
        ).all()
        assert sorted((p.side, p.starter, p.name) for p in players) == [
            ("away", False, "Remplaçant 2"),
            ("away", True, "Titulaire 2"),
            ("home", False, "Remplaçant 1"),
            ("home", True, "Titulaire 1"),
        ]
        stats = await session.scalar(
            select(PlayerMatchStats).where(PlayerMatchStats.match_id == ids[0])
        )
        assert stats is not None
        assert (stats.name, stats.goals, stats.shots_on, float(stats.rating or 0)) == (
            "Buteur",
            1,
            2,
            8.1,
        )

    # Passage suivant, même minute : la VAR annule le 2e but. Relevé mis à jour (pas de
    # doublon), événement retiré.
    answer["7000"] = _rich(7000, "2H", 60, (1, 0), var=True)
    async with db_factory() as session:
        await follow_live(session, settings, now=NOW + timedelta(minutes=2))
    async with db_factory() as session:
        assert await _count(session, MatchEvent, ids[0]) == 2
        assert await _count(session, LiveSnapshot, ids[0]) == 1
        snap = await session.scalar(select(LiveSnapshot).where(LiveSnapshot.match_id == ids[0]))
        assert snap is not None
        assert snap.home_goals == 1
        assert await _count(session, MatchLineupPlayer, ids[0]) == 4  # remplacées, pas ajoutées

    # Relecture des relevés gardés sur le disque : tout revient, sans doublon.
    async with db_factory() as session:
        for model in (MatchEvent, LiveSnapshot, MatchLineup, MatchLineupPlayer, PlayerMatchStats):
            await session.execute(delete(model))
        await session.commit()
        replay = await replay_live_files(session)
    assert (replay["files"], replay["read"], replay["missing"]) == (2, 2, 0)
    assert "Corner Kicks" in replay["stat_types"]
    async with db_factory() as session:
        assert await _count(session, LiveSnapshot, ids[0]) == 1
        assert await _count(session, MatchEvent, ids[0]) == 2  # le relevé le plus récent
        assert await _count(session, MatchLineup, ids[0]) == 2


async def test_backfill_finished_matches_then_probe(
    db_factory: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = await _two_matches(db_factory, tmp_path)
    async with db_factory() as session:
        for n, match_id in enumerate(ids):
            await session.execute(
                update(Match).where(Match.id == match_id).values(api_football_id=8000 + n)
            )
        await session.commit()
    monkeypatch.setattr(api_football.ApiFootballClient, "__init__", _fast_init)
    settings = make_settings(raw_data_dir=tmp_path / "raw", api_football_key="k" * 32)
    calls: list[str] = []
    finished = _rich(8000, "FT", 90, (2, 0))
    answer = {"8000": finished, "8001": _item(8001, "FT", 90, (0, 0), (0, 0))}
    monkeypatch.setattr(service, "api_football_transport", _transport(calls, answer))

    async with db_factory() as session:
        report = await backfill_details(session, settings, competition="EPL", max_requests=5)
    assert report["status"] == "ok", report
    assert (report["matches"], report["requests"], report["empty"]) == (2, 1, 1)
    assert report["left"] == 0  # tout est complet (en tout, pas seulement ce lot)
    assert report["not_returned"] == 0
    async with db_factory() as session:
        assert await _count(session, MatchEvent, ids[0]) == 3
        assert await _count(session, LiveSnapshot, ids[1]) == 1  # match sans détails : marqué

    # Relancé : rien à refaire, aucune requête de matchs.
    calls.clear()
    async with db_factory() as session:
        again = await backfill_details(session, settings, max_requests=5)
    assert (again["matches"], again["requests"]) == (0, 0)

    # Essai : blocs reçus, statistiques, cotes en direct ; rien d'enregistré.
    calls.clear()
    async with db_factory() as session:
        probe = await probe_live(session, settings, fixture_id=8000)
    assert probe["found"] is True
    assert probe["blocks"] == sorted(
        [
            "fixture",
            "league",
            "teams",
            "goals",
            "score",
            "events",
            "statistics",
            "lineups",
            "players",
        ]
    )
    assert probe["stat_types"] == sorted(s["type"] for s in STATS)
    assert (probe["events"], probe["lineups"], probe["players"]) == (3, 2, 1)
    odds = probe["live_odds"]
    assert (odds["available"], odds["markets"]) == (True, 2)
    assert odds["names"] == ["Fulltime Result", "Over/Under Line"]
    # Comparaison avec 1xBet (12/11/2026) : valeurs, état, heure, champs inattendus.
    assert [(c["value"], c["line"], c["odd"], c["suspended"]) for c in odds["main"]] == [
        ("Home", None, "1.45", False),
        ("Draw", None, "3.90", False),
        ("Away", None, "9.00", True),
        ("Over", "2.5", "1.80", False),
        ("Under", "2.5", "1.95", False),
    ]
    assert odds["update"] == "2026-11-12T16:55:04+00:00"
    assert odds["state"] == {
        "stopped": False, "blocked": False, "finished": False, "elapsed": 45, "seconds": "45:00",
    }  # fmt: skip
    assert odds["unknown_fields"] == ["réponse.source"]
    assert odds["bookmaker"] == []
    assert probe["raw"]["odds_live"]["response"][0]["update"] == odds["update"]
    assert [c.split("?")[0] for c in calls] == ["/fixtures", "/odds/live"]


async def test_console_live_probe_shows_odds_and_keeps_raw_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Comparaison avec 1xBet (12/11/2026) : la console montre les cotes, leur état, l'heure
    et tout champ bookmaker ; la réponse brute est rangée dans les fichiers."""
    import asyncio
    import json
    from types import SimpleNamespace

    from footprono.console import actions
    from footprono.ingestion import live

    async def fake_probe(*_: Any) -> dict[str, Any]:
        details = live.live_odds_details(
            [
                {
                    "update": "2026-11-12T16:55:04+00:00",
                    "status": {"stopped": False, "blocked": True, "finished": False},
                    "fixture": {"status": {"elapsed": 45}},
                    "odds": [
                        {"id": 59, "name": "Fulltime Result", "values": [
                            {"value": "Home", "odd": "1.45", "suspended": True}]},
                        {"id": 1, "name": "Match Goals", "bookmaker": "Bet365", "values": []},
                    ],
                }
            ]
        )  # fmt: skip
        return {
            "status": "ok", "fixture": 8000, "found": True, "match": "A - B", "state": "HT",
            "minute": 45, "blocks": ["fixture"], "events": 0, "event_kinds": [], "lineups": 0,
            "players": 0, "stat_types": [],
            "live_odds": {"available": True, "markets": 2, "names": ["Fulltime Result"],
                          **details},
            "raw": {"odds_live": {"response": ["brut"]}},
        }  # fmt: skip

    monkeypatch.setattr(live, "probe_live", fake_probe)

    class Factory:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_: Any) -> None:
            return None

    logs: list[str] = []
    ctx = SimpleNamespace(
        factory=Factory, settings=None, files_dir=tmp_path, job_id=7, log=logs.append, result=None
    )
    await actions.live_probe(ctx, {})  # type: ignore[arg-type]
    text = "\n".join(logs)
    assert "Fulltime Result · Home : 1.45 (SUSPENDUE)" in text
    assert "bloqué oui" in text
    assert "2026-11-12T16:55:04+00:00" in text
    assert "Bookmaker : [].odds[].bookmaker = 'Bet365'" in text
    assert "Autres champs : marché.bookmaker" in text
    name = ctx.result["file"]
    assert name.startswith("direct-brut-")
    assert name.endswith("-7.json")
    raw = await asyncio.to_thread((tmp_path / name).read_text)
    assert json.loads(raw) == {"odds_live": {"response": ["brut"]}}
    assert "raw" not in ctx.result
