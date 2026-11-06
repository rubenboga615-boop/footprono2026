"""Pronostics des coupes d'Europe (moteur ``engine/cups.py``), enregistrés avant les
matchs comme ceux des championnats : ils comptent de la même façon sur la page Fiabilité.

Le backtest des coupes (calculé sur les données en base) est gardé dans les réglages du
serveur (``cups_backtest``) et montré à part sur la page Fiabilité."""

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.console.models import AppSetting
from footprono.engine import cups as engine
from footprono.football.models import Match
from footprono.ingestion.sources.api_football import UNPLAYED_STATUSES
from footprono.predictions.models import MatchPrediction, PredictionRun
from footprono.predictions.service import _selection_row

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
            "level_rate": engine.LEVEL_RATE,
            "fit_from": engine.FIT_FROM.isoformat(),
            "covid_excluded": [d.isoformat() for d in engine.COVID],
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
        state = engine.build_state(matches, as_of)
        try:
            model = engine.fit_model(state.samples, as_of)
        except ValueError as exc:
            report["errors"].append(str(exc))
            upcoming = []
        features = [state.features(m) for m in upcoming]
        preds = engine.predict(model, features) if upcoming else []
        for m, f, p in zip(upcoming, features, preds, strict=True):
            g = model.goals
            session.add(
                MatchPrediction(
                    run_id=run.id, match_id=m.match_id,
                    lambda_home=p.lambda_home, lambda_away=p.lambda_away, rho=g.rho,
                    share_home=g.share_home, share_away=g.share_away,
                    markets={k: _selection_row(s) for k, s in p.markets.items()},
                    counts={},
                    context={"cup": {
                        "rating_home": round(state.rating(m.home), 1),
                        "rating_away": round(state.rating(m.away), 1),
                        "neutral": m.neutral,
                        "goals_level_home": [round(f.attack_home, 2), round(f.defence_home, 2)],
                        "goals_level_away": [round(f.attack_away, 2), round(f.defence_away, 2)],
                    }},
                )
            )  # fmt: skip
            report["competitions"][m.competition] = report["competitions"].get(m.competition, 0) + 1
        report["matches"] = len(upcoming)
        if upcoming:
            report["model"] = {
                "season": model.season, "training_matches": model.goals.matches,
                "rho": round(model.goals.rho, 4),
                "correction_home": [round(x, 4) for x in model.correction.home],
                "correction_matches": model.correction.matches,
            }  # fmt: skip
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
        "log_loss": {k: {**v, "closing_odds": None} for k, v in result.log_loss.items()},
        "by_competition": result.by_competition,
        "by_season": result.seasons,
        "hit_rate": result.hit_rate,
        "calibration_1x2": result.calibration,
        "note": (
            "Coupes d'Europe : moteur à part (note Elo commune aux championnats et aux coupes, "
            "niveaux de buts de chaque équipe). Publiés : 1X2, double chance, les deux "
            "marquent, plus/moins 0,5 but et 1,5 but à la mi-temps ; plus/moins 2,5 buts "
            "testé ici mais non publié (niveau de buts trop changeant d'une saison à "
            "l'autre). Pas d'historique de cotes des coupes : pas de comparaison au marché."
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
