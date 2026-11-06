"""Moteur des sélections : notes, marchés publiés, favoris écrasants sans pronostic,
amicaux jamais pronostiqués, API (réglage FP_NATIONS_PREDICTIONS) et page Fiabilité
(saisons simulées : des sélections de force connue)."""

import random
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.core.config import Settings
from footprono.engine import nations as engine
from footprono.ingestion import nations
from footprono.ingestion.loader import sync_reference
from footprono.predictions import nations as nation_predictions
from footprono.predictions.models import MatchPrediction

from .conftest import make_settings

Factory = async_sessionmaker[AsyncSession]


@pytest.fixture
def settings() -> Settings:
    return make_settings(nations_predictions=True)


def _m(i: int, day: date, comp: str, h: int, a: int, hg: int | None, ag: int | None,
       neutral: bool = False) -> engine.NationMatch:  # fmt: skip
    return engine.NationMatch(i, day, comp, h, a, neutral, hg is not None, hg, ag)


def test_ratings_and_published_markets() -> None:
    d = date(2024, 9, 1)
    matches = [
        _m(1, d, "WCQ_AFR", 1, 2, 2, 0),
        _m(2, d + timedelta(days=3), "AMICAL", 3, 4, 2, 0),
        _m(3, d + timedelta(days=7), "CAN", 1, 3, None, None, neutral=True),
    ]
    state = engine.build_state(matches, d + timedelta(days=7))
    # Match officiel (K = 40) : plus d'écart qu'un amical (K = 20) au même score.
    assert state.rating(1) - engine.START > state.rating(3) - engine.START > 0
    assert len(state.samples) == 1  # l'amical sert aux notes, pas à l'apprentissage
    f = state.features(matches[2])
    assert f.diff == pytest.approx(state.rating(1) - state.rating(3))  # terrain neutre
    assert engine.published("HT_1X2||draw")
    assert engine.published("EH|-2|away")
    assert engine.published("TEAM_OU_HOME|0.5|over")
    assert engine.published("OU|2.5|under")
    assert not engine.published("OU|3.5|over")
    assert not engine.published("EH|-1|home")
    assert not engine.published("CS||1-0")
    assert not engine.published("HTFT||home/home")


_TEAMS = [(f"Sélection {i}", 500 + i) for i in range(30)]


def _items(seed: int = 5) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Éliminatoires (officiels) et amicaux simulés de 2019 à 2026, buts tirés au sort."""
    rng = random.Random(seed)  # noqa: S311 (tirage reproductible, pas de sécurité)
    nrng = np.random.default_rng(seed)
    strength = {t[1]: rng.gauss(0, 0.3) for t in _TEAMS}
    official, friendly, fid, day = [], [], 1, datetime(2019, 1, 5, 18, tzinfo=UTC)
    while day < datetime(2026, 10, 30, tzinfo=UTC):
        h, a = rng.sample(_TEAMS, 2)
        hg = int(nrng.poisson(np.exp(0.3 + strength[h[1]] - strength[a[1]])))
        ag = int(nrng.poisson(np.exp(0.05 + strength[a[1]] - strength[h[1]])))
        item = {
            "fixture": {"id": fid, "date": day.isoformat(), "status": {"short": "FT"},
                        "venue": {"city": None}},
            "league": {"id": 29, "season": day.year, "round": "Group Stage - 1"},
            "teams": {"home": {"id": h[1], "name": h[0]}, "away": {"id": a[1], "name": a[0]}},
            "score": {"fulltime": {"home": hg, "away": ag},
                      "halftime": {"home": int(nrng.binomial(hg, 0.45)),
                                   "away": int(nrng.binomial(ag, 0.45))}},
        }  # fmt: skip
        (friendly if fid % 5 == 0 else official).append(item)
        fid += 1
        day += timedelta(days=1)
    return official, friendly


def _upcoming(fid: int, home: tuple[str, int], away: tuple[str, int]) -> dict[str, Any]:
    return {
        "fixture": {"id": fid, "date": "2026-11-15T19:00:00+00:00", "status": {"short": "NS"},
                    "venue": {"city": None}},
        "league": {"id": 29, "season": 2026, "round": "Group Stage - 6"},
        "teams": {"home": {"id": home[1], "name": home[0]},
                  "away": {"id": away[1], "name": away[0]}},
        "score": {"fulltime": {"home": None, "away": None},
                  "halftime": {"home": None, "away": None}},
    }  # fmt: skip


async def test_backtest_predictions_api_and_reliability(
    db_factory: Factory, client: AsyncClient, app: FastAPI
) -> None:
    official, friendly = _items()
    async with db_factory() as session:
        await sync_reference(session)
        await nations.sync_nations(session)
        await nations.load_nation_fixtures(
            session, "WCQ_AFR", [*official, _upcoming(90001, _TEAMS[0], _TEAMS[1])]
        )
        await nations.load_nation_fixtures(
            session, "AMICAL", [*friendly, _upcoming(90002, _TEAMS[2], _TEAMS[3])]
        )
        await session.commit()

        matches = await engine.load_matches(session)
        result = engine.backtest(matches, 2021, 2026)
        assert result.matches > 1000
        ll = result.log_loss
        assert ll["1X2"]["model"] < ll["1X2"]["naive"]  # le moteur apprend les forces
        assert ll["OU|2.5"]["model"] < ll["OU|2.5"]["naive"]
        assert "AFRIQUE" in result.by_competition
        model = engine.fit_model(engine.build_state(matches, date(2026, 11, 10)).samples, 2026)
        assert model.home[1] > 0  # plus d'écart de note : plus de buts
        assert 0.3 < model.share_home < 0.6

        # Favori écrasant : aucun pronostic.
        strong = engine.Features(900.0, False, 3.0, 0.3, 0.3, 3.0)
        assert engine.predict(model, [strong]) == [None]

        run = await nation_predictions.predict_nations(session, as_of=date(2026, 11, 10))
        assert run.report["matches"] + run.report["favourites"] == 1  # l'amical : jamais
        preds = list(
            await session.scalars(select(MatchPrediction).where(MatchPrediction.run_id == run.id))
        )
        await nation_predictions.refresh_backtest(session, today=date(2026, 11, 10))
    if not preds:
        pytest.skip("match simulé jugé écrasant : rien à publier")
    pred = preds[0]
    assert all(engine.published(k) for k in pred.markets)
    assert {"1X2||home", "DC||X2", "BTTS||yes", "HT_1X2||draw", "EH|1|away"} <= set(pred.markets)
    match_id = pred.match_id

    params = {"date_from": "2026-11-10", "nations": "true"}
    listed = (await client.get("/api/v1/predictions/upcoming", params=params)).json()
    shown = {u["match"]["id"]: u for u in listed}
    assert match_id in shown
    assert shown[match_id]["prediction"]["over_2_5"] is not None
    assert all(u["match"]["competition"] != "AMICAL" for u in listed)  # amicaux : jamais
    old_app = (
        await client.get("/api/v1/predictions/upcoming", params={"date_from": "2026-11-10"})
    ).json()
    assert all(u["match"]["id"] != match_id for u in old_app)
    app.state.settings = make_settings(nations_predictions=False)
    hidden = (await client.get("/api/v1/predictions/upcoming", params=params)).json()
    assert all(u["match"]["id"] != match_id for u in hidden)
    app.state.settings = make_settings(nations_predictions=True)

    rel = (await client.get("/api/v1/reliability", params={"competition": "wcq_afr"})).json()
    assert rel["backtest"]["engine_version"] == engine.ENGINE_VERSION
    assert rel["backtest"]["log_loss"]["BTTS"]["closing_odds"] is None
