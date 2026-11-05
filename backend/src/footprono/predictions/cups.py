"""Pronostics des coupes d'Europe (moteur ``engine/cups.py``), enregistrés avant les
matchs comme ceux des championnats : ils comptent de la même façon sur la page Fiabilité.

Le backtest des coupes (calculé sur les données en base) est gardé dans les réglages du
serveur (``cups_backtest``) et montré à part sur la page Fiabilité."""

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.console.models import AppSetting
from footprono.engine import cups as engine
from footprono.football.models import Match
from footprono.ingestion.sources.api_football import UNPLAYED_STATUSES
from footprono.predictions.models import MatchPrediction, PredictionRun

BACKTEST_KEY = "cups_backtest"
BACKTEST_FROM = date(2022, 7, 1)


async def predict_cups(
    session: AsyncSession, as_of: date | None = None, days_ahead: int = 10
) -> PredictionRun:
    as_of = as_of or datetime.now(UTC).date()
    run = PredictionRun(
        engine_version=engine.ENGINE_VERSION, as_of=as_of, status="running",
        parameters={
            "days_ahead": days_ahead, "k": [engine.K_LEAGUE, engine.K_CUP],
            "home": [engine.HOME_LEAGUE, engine.HOME_CUP],
            "start": [engine.START_LEAGUE, engine.START_FOREIGN],
        },
        report={},
    )  # fmt: skip
    session.add(run)
    await session.commit()
    matches = await engine.load_matches(session)
    unplayed = set(
        await session.scalars(select(Match.id).where(Match.api_status.in_(UNPLAYED_STATUSES)))
    )
    end = as_of + timedelta(days=days_ahead)
    upcoming = [
        m for m in matches
        if m.cup and not m.finished and as_of <= m.day <= end and m.match_id not in unplayed
    ]  # fmt: skip
    report: dict[str, Any] = {"matches": 0, "competitions": {}, "errors": []}
    if upcoming:
        ratings = engine.build_ratings(matches, as_of)
        try:
            theta = engine.fit_mapping(ratings.samples)
        except ValueError as exc:
            report["errors"].append(str(exc))
            upcoming = []
        for m in upcoming:
            diff = ratings.diff(m)
            p = engine.probabilities(theta, np.array([diff]))[0]
            session.add(
                MatchPrediction(
                    run_id=run.id, match_id=m.match_id,
                    # Pas de modèle des buts pour les coupes : buts attendus non publiés.
                    lambda_home=0.0, lambda_away=0.0, rho=0.0, share_home=0.0, share_away=0.0,
                    markets=engine.markets(float(p[0]), float(p[1]), float(p[2])),
                    counts={},
                    context={"cup": {
                        "rating_home": round(ratings.rating(m.home), 1),
                        "rating_away": round(ratings.rating(m.away), 1),
                        "neutral": m.neutral,
                    }},
                )
            )  # fmt: skip
            report["competitions"][m.competition] = report["competitions"].get(m.competition, 0) + 1
        report["matches"] = len(upcoming)
        report["mapping"] = [round(x, 5) for x in theta] if upcoming else None
    run.report = report
    run.status = "ok" if not report["errors"] else "partial"
    run.finished_at = datetime.now(UTC)
    await session.commit()
    return run


async def refresh_backtest(session: AsyncSession) -> dict[str, Any]:
    """Backtest des coupes sur les données en base, gardé pour la page Fiabilité."""
    result = engine.backtest(await engine.load_matches(session), BACKTEST_FROM)
    value = {
        "label": "Backtest des coupes d'Europe : simulation sur des saisons passées",
        "verified_on": datetime.now(UTC).date().isoformat(),
        "seasons": f"{BACKTEST_FROM.year}-{(BACKTEST_FROM.year + 1) % 100:02d} à aujourd'hui",
        "matches": result.matches,
        "engine_version": engine.ENGINE_VERSION,
        "log_loss": {
            "1X2": {"model": result.log_loss, "naive": result.naive_log_loss, "closing_odds": None}
        },
        "by_competition": result.by_competition,
        "hit_rate": result.hit_rate,
        "calibration_1x2": result.calibration,
        "note": (
            "Coupes d'Europe : moteur à part (note Elo commune aux championnats et aux coupes, "
            "résultats seulement) ; 1X2 et double chance seulement. Pas d'historique de cotes "
            "des coupes : pas de comparaison au marché."
        ),
    }
    row = await session.get(AppSetting, BACKTEST_KEY)
    if row is None:
        session.add(AppSetting(key=BACKTEST_KEY, value=json.dumps(value)))
    else:
        row.value = json.dumps(value)
    await session.commit()
    return value


async def stored_backtest(session: AsyncSession) -> dict[str, Any] | None:
    row = await session.get(AppSetting, BACKTEST_KEY)
    return json.loads(row.value) if row else None
