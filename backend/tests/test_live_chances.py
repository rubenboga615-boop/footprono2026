"""Chances en direct (plan du 10/11/2026, étape 6) : vérification sur les matchs joués,
calcul pendant le match, publication refusée tant que la vérification n'est pas juste."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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


async def test_study_of_played_matches(db_factory: Factory, tmp_path: Path) -> None:
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
    # Convention « contre son camp » inversée : 2 buts pour le domicile, 1 pour l'extérieur.
    assert rep["matches"] == 1
    assert rep["inconsistent"] == 1
    checkpoints = {r["checkpoint"] for r in rep["rows"]}
    assert checkpoints == {"15'", "30'", "60'", "75'"}
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

    good = {"rows": [row(c, "juste") for c in ("15'", "30'", "60'", "75'")]}
    assert _live_verdict(good)[0] is True
    bad = {"rows": [*good["rows"][:3], row("75'", "à revoir")]}
    ok, lines = _live_verdict(bad)
    assert ok is False
    assert lines[-1] == "75' : 1 marchés vérifiés, à revoir : Résultat (1X2)"
    assert _live_verdict({"rows": good["rows"][:3]})[0] is False  # 75' : trop peu


def test_backfill_offers_cups_and_national_teams() -> None:
    from footprono.console.registry import get_action

    param = next(p for p in get_action("details_backfill").params if p.name == "competition")
    codes = [code for code, _ in param.choices()]
    assert codes[0] == ""  # Tous : championnats, coupes et sélections
    assert {"EPL", "ISR", "UCL", "UEL", "UECL", "UNL", "WCQ_EUR", "CAN"} <= set(codes)
