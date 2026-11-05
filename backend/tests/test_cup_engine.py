"""Moteur des coupes d'Europe : notes, correspondance, backtest, pronostics enregistrés,
API et page Fiabilité (coupes simulées : des équipes de force connue)."""

import random
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.engine import cups as engine
from footprono.football.analysis import match_analysis
from footprono.football.models import Match, MatchStatus
from footprono.ingestion import cups
from footprono.ingestion.loader import sync_reference
from footprono.predictions import cups as cup_predictions
from footprono.predictions.models import MatchPrediction

Factory = async_sessionmaker[AsyncSession]


def _m(i: int, day: date, comp: str, h: int, a: int, hg: int | None, ag: int | None,
       neutral: bool = False) -> engine.CupMatch:  # fmt: skip
    return engine.CupMatch(i, day, comp, h, a, neutral, hg is not None, hg, ag)


def test_ratings_start_and_home_advantage() -> None:
    d = date(2024, 9, 1)
    matches = [
        _m(1, d, "EPL", 1, 2, 3, 0),  # 1 et 2 : équipes de nos championnats
        _m(2, d + timedelta(days=7), "UCL", 1, 99, None, None),  # 99 : équipe d'ailleurs
        _m(3, d + timedelta(days=8), "UCL", 1, 99, None, None, neutral=True),
    ]
    r = engine.build_ratings(matches, d + timedelta(days=7))
    assert r.rating(1) > engine.START_LEAGUE > r.rating(2)
    assert r.rating(99) == engine.START_FOREIGN
    assert r.diff(matches[1]) == pytest.approx(r.rating(1) + engine.HOME_CUP - 1350)
    assert r.diff(matches[2]) == pytest.approx(r.rating(1) - 1350)  # finale : terrain neutre
    m = engine.markets(0.5, 0.3, 0.2)
    assert m["DC||1X"][0] == pytest.approx(0.8)
    assert m["DC||12"][0] == pytest.approx(0.7)


def _season_items(seed: int = 3) -> list[dict[str, Any]]:
    """Coupes simulées 2019-2025 : 24 équipes de force fixe, résultats tirés au sort."""
    rng = random.Random(seed)  # noqa: S311 (tirage reproductible, pas de sécurité)
    strength = {100 + i: rng.gauss(0, 250) for i in range(24)}
    items, fid, day = [], 1, datetime(2019, 9, 1, 19, tzinfo=UTC)
    while day < datetime(2025, 12, 1, tzinfo=UTC):
        h, a = rng.sample(sorted(strength), 2)
        d = strength[h] + 80 - strength[a]
        p_home = 1 / (1 + 10 ** (-d / 400)) * 0.78
        p_draw = 0.24
        u = rng.random()
        hg, ag = (2, 0) if u < p_home else (1, 1) if u < p_home + p_draw else (0, 1)
        season = day.year if day.month >= 7 else day.year - 1
        items.append({
            "fixture": {"id": fid, "date": day.isoformat(), "status": {"short": "FT"}},
            "league": {"id": 2, "season": season, "round": "League Stage - 1"},
            "teams": {"home": {"id": h, "name": f"Club {h}"},
                      "away": {"id": a, "name": f"Club {a}"}},
            "score": {"fulltime": {"home": hg, "away": ag}, "halftime": {"home": 0, "away": 0}},
        })  # fmt: skip
        fid += 1
        day += timedelta(days=1 if day.month not in (6, 7) else 3)
    return items


async def test_backtest_predictions_api_and_reliability(
    db_factory: Factory, client: AsyncClient
) -> None:
    items = _season_items()
    upcoming = {
        "fixture": {"id": 99999, "date": "2026-11-25T20:00:00+00:00", "status": {"short": "NS"}},
        "league": {"id": 2, "season": 2026, "round": "League Stage - 5"},
        "teams": {"home": {"id": 100, "name": "Club 100"}, "away": {"id": 101, "name": "Club 101"}},
        "score": {"fulltime": {"home": None, "away": None},
                  "halftime": {"home": None, "away": None}},
    }  # fmt: skip
    async with db_factory() as session:
        await sync_reference(session)
        await cups.sync_cups(session)
        await cups.load_cup_fixtures(session, "UCL", [*items, upcoming])
        await session.commit()

        result = engine.backtest(await engine.load_matches(session), date(2022, 7, 1))
        assert result.matches > 500
        assert result.log_loss < result.naive_log_loss  # le moteur apprend les forces
        theta = engine.fit_mapping(engine.build_ratings(await engine.load_matches(session),
                                                        date(2026, 11, 20)).samples)  # fmt: skip
        assert theta[2] > 0  # plus d'écart de note : plus de chances à domicile

        run = await cup_predictions.predict_cups(session, as_of=date(2026, 11, 20))
        assert run.report["matches"] == 1
        pred = await session.scalar(select(MatchPrediction).where(MatchPrediction.run_id == run.id))
        assert pred is not None
        assert set(pred.markets) == {"1X2||home", "1X2||draw", "1X2||away", "DC||1X", "DC||X2",
                                     "DC||12"}  # fmt: skip
        assert sum(pred.markets[k][0] for k in ("1X2||home", "1X2||draw", "1X2||away")) == (
            pytest.approx(1, abs=1e-4)
        )
        match_id = pred.match_id
        await cup_predictions.refresh_backtest(session)

    r = await client.get(f"/api/v1/matches/{match_id}/prediction")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["expected_goals"] is None
    assert {m["market"] for m in body["markets"]} == {"1X2"}  # double chance : Premium
    detail = await client.get(f"/api/v1/matches/{match_id}")
    assert detail.status_code == 200, detail.text
    async with db_factory() as session:  # analyse détaillée (Premium) : forme, confrontations
        analysis = await match_analysis(session, match_id)
    assert analysis
    old_app = (
        await client.get("/api/v1/predictions/upcoming", params={"date_from": "2026-11-20"})
    ).json()
    assert all(u["match"]["id"] != match_id for u in old_app)  # ancienne application : rien
    upcoming_list = (
        await client.get(
            "/api/v1/predictions/upcoming", params={"date_from": "2026-11-20", "cups": "true"}
        )
    ).json()
    cup = next(u for u in upcoming_list if u["match"]["id"] == match_id)
    assert cup["prediction"]["over_2_5"] is None

    # Résultat du match : il compte sur la page Fiabilité, filtre de la coupe.
    async with db_factory() as session:
        match = await session.get(Match, match_id)
        assert match is not None
        match.status, match.home_goals, match.away_goals = MatchStatus.FINISHED, 1, 0
        await session.commit()
    rel = (await client.get("/api/v1/reliability", params={"competition": "ucl"})).json()
    assert rel["matches"] == 1
    assert rel["backtest"]["matches"] == result.matches
    ou = next(m for m in rel["markets"] if m["market"] == "OU|2.5")
    assert "Coupes d'Europe" in ou["warning"]
    assert np.isfinite(rel["markets"][0]["log_loss"])
