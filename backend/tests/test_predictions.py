"""Prédictions enregistrées et API, sur une saison réelle dont la fin est « à venir »."""

import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.engine import ENGINE_VERSION
from footprono.football.models import DataSource, Match, MatchStatus
from footprono.ingestion.service import IngestionRequest, run_ingestion
from footprono.predictions.models import MatchPrediction
from footprono.predictions.service import predict_upcoming, prediction_needed

from .conftest import make_premium, make_settings

FIXTURES = Path(__file__).parent / "fixtures"
AS_OF = date(2025, 5, 18)  # les deux dernières journées de 2024-25 deviennent « à venir »


@pytest.fixture
async def upcoming(db_factory: async_sessionmaker[AsyncSession], tmp_path: Path) -> list[int]:
    await run_ingestion(
        db_factory,
        make_settings(raw_data_dir=tmp_path),
        [
            IngestionRequest(DataSource.FOOTBALL_DATA, ["EPL"], [2024], FIXTURES / "football-data"),
            IngestionRequest(DataSource.UNDERSTAT, ["EPL"], [2024], FIXTURES / "understat"),
        ],
    )
    async with db_factory() as session:
        await session.execute(
            update(Match)
            .where(Match.match_date >= AS_OF)
            .values(
                status=MatchStatus.SCHEDULED,
                home_goals=None,
                away_goals=None,
                home_goals_ht=None,
                away_goals_ht=None,
            )
        )
        await session.commit()
        return list(await session.scalars(select(Match.id).where(Match.match_date >= AS_OF)))


async def test_predict_upcoming_stores_coherent_predictions(
    db_factory: async_sessionmaker[AsyncSession], upcoming: list[int]
) -> None:
    assert len(upcoming) >= 10
    async with db_factory() as session:
        run = await predict_upcoming(session, AS_OF, days_ahead=30)
        assert run.status == "ok"
        assert run.engine_version == ENGINE_VERSION
        assert run.report["competitions"]["EPL"]["matches"] == len(upcoming)
        preds = (await session.scalars(select(MatchPrediction))).all()
    assert sorted(p.match_id for p in preds) == sorted(upcoming)
    for p in preds:
        one_x_two = sum(p.markets[f"1X2||{s}"][0] for s in ("home", "draw", "away"))
        assert one_x_two == pytest.approx(1.0, abs=1e-5)
        over = p.markets["OU|2.5|over"][0] + p.markets["OU|2.5|under"][0]
        assert over == pytest.approx(1.0, abs=1e-5)
        assert 0.2 < p.lambda_home < 4
        assert 0.2 < p.lambda_away < 4
        assert "CORNERS_OU|9.5|over" in p.markets
        assert "BOOKING_POINTS_OU|45.5|over" in p.markets
        assert p.counts["corners"]["mean_home"] > 0
        assert p.context["points"][0] >= 0


async def test_prediction_api(
    db_factory: async_sessionmaker[AsyncSession], upcoming: list[int], client: AsyncClient
) -> None:
    missing = await client.get(f"/api/v1/matches/{upcoming[0]}/prediction")
    assert missing.status_code == 404

    async with db_factory() as session:
        await predict_upcoming(session, AS_OF, days_ahead=30)

    detail = await client.get(f"/api/v1/matches/{upcoming[0]}/prediction")
    assert detail.status_code == 200
    body = detail.json()
    assert body["engine_version"] == ENGINE_VERSION
    one_x_two = [m for m in body["markets"] if m["market"] == "1X2"]
    assert len(one_x_two) == 3
    for m in one_x_two:
        assert m["fair_odds"] == pytest.approx(1 / m["probability"], rel=1e-3)
    # Sans compte : version gratuite (1X2, OU, BTTS) ; le reste est signalé, pas caché.
    assert {m["market"] for m in body["markets"]} == {"1X2", "OU", "BTTS"}
    assert body["plan"] == "free"
    assert "AH" in body["locked_markets"]
    assert body["counts"] is None
    ah = await client.get(f"/api/v1/matches/{upcoming[0]}/prediction", params={"market": "ah"})
    assert ah.json()["markets"] == []
    signup = await client.post(
        "/api/v1/auth/register",
        json={"phone": "+22997333333", "password": "12345678", "display_name": "Ama",
              "country": "CI", "adult": True},
    )  # fmt: skip
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    await make_premium(db_factory, "+22997333333")
    ah = await client.get(
        f"/api/v1/matches/{upcoming[0]}/prediction", params={"market": "ah"}, headers=headers
    )
    assert {m["market"] for m in ah.json()["markets"]} == {"AH"}
    assert ah.json()["plan"] == "premium"
    assert ah.json()["counts"]["corners"]["mean_home"] > 0

    listing = await client.get(
        "/api/v1/predictions/upcoming", params={"date_from": "2025-05-18", "date_to": "2025-06-30"}
    )
    assert listing.status_code == 200
    items = listing.json()
    assert len(items) == len(upcoming)
    assert all(item["prediction"] is not None for item in items)
    first = items[0]["prediction"]
    total = (
        first["home"]["probability"] + first["draw"]["probability"] + first["away"]["probability"]
    )
    assert total == pytest.approx(1.0, abs=1e-5)

    runs = await client.get("/api/v1/predictions/runs")
    assert runs.status_code == 200
    assert runs.json()[0]["status"] == "ok"


async def test_reliability_counts_only_predictions_made_before_kickoff(
    db_factory: async_sessionmaker[AsyncSession], upcoming: list[int], client: AsyncClient
) -> None:
    empty = (await client.get("/api/v1/reliability")).json()
    assert empty["matches"] == 0
    assert empty["warning"] is not None
    assert empty["backtest"]["matches"] == 7081

    async with db_factory() as session:
        await predict_upcoming(session, AS_OF, days_ahead=30)
        scores = [(2, 1), (1, 1), (0, 2), (3, 0)]
        ids = sorted(upcoming)
        for i, mid in enumerate(ids):
            hg, ag = scores[i % len(scores)]
            await session.execute(
                update(Match)
                .where(Match.id == mid)
                .values(status=MatchStatus.FINISHED, home_goals=hg, away_goals=ag)
            )
        # Prédictions « faites la veille », sauf une enregistrée après le match : exclue.
        await session.execute(
            text(
                "UPDATE match_predictions mp SET created_at = "
                "(m.match_date - 1)::timestamp AT TIME ZONE 'UTC' "
                "FROM matches m WHERE m.id = mp.match_id"
            )
        )
        await session.execute(
            update(MatchPrediction)
            .where(MatchPrediction.match_id == ids[0])
            .values(created_at=datetime.now(UTC))
        )
        await session.commit()
        preds = {
            p.match_id: p
            for p in await session.scalars(
                select(MatchPrediction).where(MatchPrediction.match_id != ids[0])
            )
        }

    report = (await client.get("/api/v1/reliability", params={"competition": "epl"})).json()
    n = len(ids) - 1
    assert report["matches"] == n
    assert report["enough_data"] is False
    assert "trop petit" in report["warning"]
    one_x_two = next(m for m in report["markets"] if m["market"] == "1X2")
    # log loss recalculée à la main sur les prédictions stockées
    expected = 0.0
    for i, mid in enumerate(ids[1:], start=1):
        hg, ag = scores[i % len(scores)]
        key = "home" if hg > ag else ("draw" if hg == ag else "away")
        expected -= math.log(preds[mid].markets[f"1X2||{key}"][0])
    assert one_x_two["log_loss"] == pytest.approx(expected / n, abs=1e-4)
    assert sum(b["count"] for b in one_x_two["calibration"]) == 3 * n
    assert sum(one_x_two["observed_frequencies"].values()) == pytest.approx(1, abs=1e-3)
    assert len(report["recent"]) == min(20, n)
    assert ids[0] not in {r["match_id"] for r in report["recent"]}
    # les cotes de clôture de football-data servent de référence
    versus = {v["market"]: v for v in report["versus_closing_odds"]}
    assert versus["1X2"]["matches"] == n

    other = (await client.get("/api/v1/reliability", params={"competition": "L1"})).json()
    assert other["matches"] == 0


async def test_prediction_needed_catches_up_after_downtime_and_new_fixtures(
    db_factory: async_sessionmaker[AsyncSession], upcoming: list[int]
) -> None:
    now = datetime(2025, 5, 18, 12, tzinfo=UTC)
    async with db_factory() as session:
        assert await prediction_needed(session, now=now) == "aucune prédiction enregistrée"
        run = await predict_upcoming(session, AS_OF, days_ahead=30)
        assert run.finished_at is not None
        ran_at = run.finished_at
        assert set(run.report["window"]) == set(upcoming)
        # À jour : rien à refaire (fenêtre de 30 jours comme l'exécution). Les matchs
        # du jeu de test datent de 2025 : « maintenant » est placé à cette date.
        assert await prediction_needed(session, now=now, days_ahead=30) is None
        # Serveur éteint plus de 12 h : on relance.
        stale = await prediction_needed(session, now=ran_at + timedelta(hours=13), days_ahead=30)
        assert stale is not None
        assert "plus de 12 h" in stale
        # Un match arrivé au calendrier depuis (jamais examiné) : on relance.
        newcomer = upcoming[0]
        await session.execute(delete(MatchPrediction).where(MatchPrediction.match_id == newcomer))
        run.report = {**run.report, "window": [m for m in upcoming if m != newcomer]}
        await session.commit()
        reason = await prediction_needed(session, now=now, days_ahead=30)
        assert reason == "1 match(s) à venir sans prédiction"
        # Examiné mais non prédit (erreur signalée) : pas de relance en boucle.
        run.report = {**run.report, "window": upcoming}
        await session.commit()
        assert await prediction_needed(session, now=now, days_ahead=30) is None


async def test_level_2_league_predicted_without_btts(
    db_factory: async_sessionmaker[AsyncSession], tmp_path: Path, client: AsyncClient
) -> None:
    """Belgique (niveau 2) : prédite avec les xG tirés des tirs, sans « les deux marquent »
    ni corners/cartons ; la liste des matchs reste lisible (pas de « les deux marquent »)."""
    await run_ingestion(
        db_factory,
        make_settings(raw_data_dir=tmp_path),
        [IngestionRequest(DataSource.FOOTBALL_DATA, ["BEL"], [2024], FIXTURES / "football-data")],
    )
    as_of = date(2025, 2, 1)
    async with db_factory() as session:
        await session.execute(
            update(Match)
            .where(Match.match_date >= as_of)
            .values(status=MatchStatus.SCHEDULED, home_goals=None, away_goals=None,
                    home_goals_ht=None, away_goals_ht=None)
        )  # fmt: skip
        await session.commit()
        run = await predict_upcoming(session, as_of, days_ahead=60)
        assert run.status == "ok", run.report
        assert run.report["competitions"]["BEL"]["data_level"] == 2
        preds = list(await session.scalars(select(MatchPrediction)))
    assert preds
    for p in preds:
        assert not any(k.startswith(("BTTS|", "1X2_BTTS|", "OU_BTTS|")) for k in p.markets)
        assert "OU|2.5|over" in p.markets
        assert not p.counts  # corners, cartons, tirs : non mesurés à ce niveau

    listing = await client.get(
        "/api/v1/predictions/upcoming", params={"date_from": "2025-02-01", "date_to": "2025-04-01"}
    )
    assert listing.status_code == 200
    items = [i for i in listing.json() if i["prediction"] is not None]
    assert items
    assert all(i["prediction"]["both_score"] is None for i in items)


async def test_level_stretch_reused_from_a_recent_run(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """L'écart favori / outsider (long à calculer) est repris d'une exécution réussie de la
    même version du moteur au cours des 7 derniers jours ; sinon il est recalculé."""
    from footprono.predictions.models import PredictionRun
    from footprono.predictions.service import _recent_stretches

    today = date(2026, 10, 10)

    def run(as_of: date, stretch: dict[str, float], version: str = ENGINE_VERSION) -> PredictionRun:
        return PredictionRun(
            engine_version=version, as_of=as_of, status="ok", report={},
            parameters={"level_stretch": stretch},
        )  # fmt: skip

    async with db_factory() as session:
        session.add_all(
            [
                run(today - timedelta(days=9), {"BEL": 0.2}),  # trop ancienne
                run(today - timedelta(days=3), {"POR": 0.1, "NED": 0.0}),
                run(today - timedelta(days=1), {"POR": 0.15}),  # la plus récente l'emporte
                run(today, {"GRE": 0.3}, version="0.0"),  # autre version du moteur
            ]
        )
        await session.commit()
        assert await _recent_stretches(session, today) == {"POR": 0.15, "NED": 0.0}
