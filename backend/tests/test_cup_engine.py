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


PUBLISHED = {
    "1X2||home", "1X2||draw", "1X2||away", "DC||1X", "DC||X2", "DC||12", "BTTS||yes",
    "BTTS||no", "OU|0.5|over", "OU|0.5|under", "HT_OU|1.5|over", "HT_OU|1.5|under",
}  # fmt: skip


def test_ratings_levels_and_published_markets() -> None:
    d = date(2024, 9, 1)
    matches = [
        _m(1, d, "EPL", 1, 2, 3, 0),  # 1 et 2 : équipes de nos championnats
        _m(2, d + timedelta(days=7), "UCL", 1, 99, None, None),  # 99 : équipe d'ailleurs
        _m(3, d + timedelta(days=8), "UCL", 1, 99, None, None, neutral=True),
    ]
    state = engine.build_state(matches, d + timedelta(days=7))
    assert state.rating(1) > engine.START_LEAGUE > state.rating(2)
    assert state.rating(99) == engine.START_FOREIGN
    assert state.diff(matches[1]) == pytest.approx(state.rating(1) + engine.HOME_CUP - 1350)
    assert state.diff(matches[2]) == pytest.approx(state.rating(1) - 1350)  # finale : neutre
    f = state.features(matches[1])
    # Niveaux de buts : 3 marqués par l'équipe 1, rien encore pour l'équipe d'ailleurs.
    assert f.attack_home > engine.LEVEL_START
    assert f.defence_home < engine.LEVEL_START
    assert f.attack_away == engine.LEVEL_START
    assert f.pool == 1.0  # club de nos championnats contre un club d'ailleurs
    assert not state.samples  # aucun match de coupe joué
    # Marchés publiés : ceux qui ont passé l'étude seulement.
    assert engine.published("OU|0.5|over")
    assert engine.published("HT_OU|1.5|under")
    assert engine.published("DC||X2")
    assert not engine.published("OU|2.5|over")
    assert not engine.published("EH|-1|home")
    assert not engine.published("CS||1-0")


def test_correction_moves_home_probability_only() -> None:
    p = np.array([[0.35, 0.3, 0.35], [0.75, 0.15, 0.10]])
    c = engine.Correction(home=(0.1, 1.0))
    q = c.apply(p)
    assert q[0, 0] > 0.35  # le domicile gagne un peu
    assert q[:, 2] == pytest.approx(p[:, 2] / q.sum(axis=1) * 1, rel=0.05)
    assert q.sum(axis=1) == pytest.approx([1, 1])
    assert engine.Correction().apply(p) == pytest.approx(p)


def _season_items(seed: int = 3) -> list[dict[str, Any]]:
    """Coupes simulées 2019-2025 : 24 équipes de force fixe, buts tirés au sort (Poisson)."""
    rng = random.Random(seed)  # noqa: S311 (tirage reproductible, pas de sécurité)
    nrng = np.random.default_rng(seed)
    strength = {100 + i: rng.gauss(0, 0.35) for i in range(24)}
    items, fid, day = [], 1, datetime(2019, 9, 1, 19, tzinfo=UTC)
    while day < datetime(2025, 12, 1, tzinfo=UTC):
        h, a = rng.sample(sorted(strength), 2)
        hg = int(nrng.poisson(np.exp(0.35 + strength[h] - strength[a])))
        ag = int(nrng.poisson(np.exp(0.1 + strength[a] - strength[h])))
        hh, ah = int(nrng.binomial(hg, 0.45)), int(nrng.binomial(ag, 0.45))
        season = day.year if day.month >= 7 else day.year - 1
        items.append({
            "fixture": {"id": fid, "date": day.isoformat(), "status": {"short": "FT"}},
            "league": {"id": 2, "season": season, "round": "League Stage - 1"},
            "teams": {"home": {"id": h, "name": f"Club {h}"},
                      "away": {"id": a, "name": f"Club {a}"}},
            "score": {"fulltime": {"home": hg, "away": ag}, "halftime": {"home": hh, "away": ah}},
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

        matches = await engine.load_matches(session)
        result = engine.backtest(matches, date(2022, 7, 1))
        assert result.matches > 500
        ll = result.log_loss
        assert ll["1X2"]["model"] < ll["1X2"]["naive"]  # le moteur apprend les forces
        assert ll["OU|2.5"]["model"] < ll["OU|2.5"]["naive"]  # et les buts
        assert [s["season"] for s in result.seasons] == [2022, 2023, 2024, 2025]
        model = engine.fit_model(engine.build_state(matches, date(2026, 11, 20)).samples,
                                 date(2026, 11, 20))  # fmt: skip
        assert model.season == 2026
        assert model.goals.home[1] > 0  # plus d'écart de note : plus de buts à domicile
        assert model.correction.matches > 0  # corrigé par les saisons 2022 à 2025
        assert 0.3 < model.goals.share_home < 0.6

        run = await cup_predictions.predict_cups(session, as_of=date(2026, 11, 20))
        assert run.report["matches"] == 1
        pred = await session.scalar(select(MatchPrediction).where(MatchPrediction.run_id == run.id))
        assert pred is not None
        assert set(pred.markets) == PUBLISHED
        assert pred.lambda_home > 0
        assert pred.lambda_away > 0
        assert pred.markets["DC||1X"][0] == pytest.approx(
            pred.markets["1X2||home"][0] + pred.markets["1X2||draw"][0], abs=1e-5
        )
        assert sum(pred.markets[k][0] for k in ("1X2||home", "1X2||draw", "1X2||away")) == (
            pytest.approx(1, abs=1e-4)
        )
        match_id = pred.match_id
        await cup_predictions.refresh_backtest(session)

    r = await client.get(f"/api/v1/matches/{match_id}/prediction")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["expected_goals"]["home"] > 0
    # Version gratuite : 1X2, plus/moins et les deux marquent ; double chance et mi-temps :
    # Premium.
    assert {m["market"] for m in body["markets"]} == {"1X2", "OU", "BTTS"}
    assert set(body["locked_markets"]) == {"DC", "HT_OU"}
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
    assert cup["prediction"]["over_2_5"] is None  # plus/moins 2,5 : non publié en coupe
    assert cup["prediction"]["both_score"] is not None
    assert cup["prediction"]["expected_goals"] is not None

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
    btts = next(m for m in rel["markets"] if m["market"] == "BTTS")
    assert btts["matches"] == 1  # « les deux marquent » est publié pour les coupes
    assert rel["backtest"]["log_loss"]["BTTS"]["closing_odds"] is None
    assert np.isfinite(rel["markets"][0]["log_loss"])
