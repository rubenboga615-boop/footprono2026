"""Étude « mélange moteur + marché » (point 1 du testeur, 24/11/2026), étape 1.

Prévisions du moteur 1 strictement hors échantillon (backtest, réestimation chaque semaine,
couche de correction comme en production), plus les cotes Pinnacle d'ouverture et de
clôture de football-data, enregistrées dans un fichier .npz pour l'analyse.

    FP_DATABASE_URL=… python blend_predict.py sortie.npz
"""

import asyncio
import sys

import numpy as np

from footprono.engine.cli import _load, predict
from footprono.engine.correction import DEFAULT_FEATURES
from footprono.engine.goals import GoalsConfig

COMPETITIONS = ["EPL", "LA_LIGA", "SERIE_A", "BUNDESLIGA", "LIGUE_1", "POR", "NED"]
SEASONS = list(range(2019, 2026))  # 2019-20 → 2025-26


def main(out: str) -> None:
    hist = asyncio.run(_load())
    pred = predict(hist, COMPETITIONS, SEASONS, GoalsConfig(), DEFAULT_FEATURES)
    rows = np.array(pred.row)
    np.savez_compressed(
        out,
        competition=np.array(pred.competition),
        season=np.array(pred.season),
        date=hist.date[rows].astype("datetime64[D]").astype(str),
        model_1x2=np.array(pred.model_1x2),
        outcome_1x2=np.array(pred.outcome_1x2),
        model_ou25=np.array(pred.model_ou25),
        outcome_ou25=np.array(pred.outcome_ou25),
        model_btts=np.array(pred.model_btts),
        outcome_btts=np.array(pred.outcome_btts),
        pre_1x2=hist.odds["pre_1x2"][rows],
        close_1x2=hist.odds["close_1x2"][rows],
        pre_ou25=hist.odds["pre_ou25"][rows],
        close_ou25=hist.odds["close_ou25"][rows],
    )
    print(len(rows), "matchs")


if __name__ == "__main__":
    main(sys.argv[1])
