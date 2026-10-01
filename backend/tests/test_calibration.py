"""Calibration détaillée : métriques, référence naïve causale, alertes ciblées."""

import numpy as np

from footprono.engine.backtest import Predictions
from footprono.engine.calibration import (
    GOAL_GROUPS,
    calibration_report,
    format_calibration,
    goal_rows,
)
from footprono.engine.history import History
from footprono.engine.scores import score_distribution

SHARE, RHO = 0.44, -0.05
COMPS = ("EPL", "LIGUE_1")
SEASONS = (2021, 2022, 2023, 2024)  # 2021 : historique pour la référence naïve


def _world(
    per_cell: int, bias_cell: tuple[str, int] | None, seed: int
) -> tuple[History, Predictions]:
    rng = np.random.default_rng(seed)
    comp, season, true_h, true_a = [], [], [], []
    for c in COMPS:
        for s in SEASONS:
            comp += [c] * per_cell
            season += [s] * per_cell
            true_h += list(rng.uniform(0.7, 2.4, per_cell))
            true_a += list(rng.uniform(0.5, 1.8, per_cell))
    n = len(comp)
    th, ta = np.array(true_h), np.array(true_a)
    hg, ag, hht, aht = (np.zeros(n) for _ in range(4))
    for i in range(n):
        joint = score_distribution(th[i], ta[i], RHO, SHARE, SHARE).joint
        flat = rng.choice(joint.size, p=joint.ravel() / joint.sum())
        hht[i], aht[i], hg[i], ag[i] = np.unravel_index(flat, joint.shape)
    hist = History(
        match_id=np.arange(n), competition=np.array(comp), season=np.array(season),
        date=np.datetime64("2021-08-01") + np.arange(n).astype("timedelta64[h]"),
        home=np.zeros(n, dtype=np.int64), away=np.ones(n, dtype=np.int64),
        finished=np.ones(n, dtype=bool), excluded=np.zeros(n, dtype=bool),
        hg=hg, ag=ag, hht=hht, aht=aht, hxg=np.full(n, np.nan), axg=np.full(n, np.nan),
    )  # fmt: skip
    test = [i for i in range(n) if season[i] >= 2022]
    # Le « moteur » voit les vrais buts attendus, sauf dans la case biaisée (+40 %).
    factor = [1.4 if bias_cell and (comp[i], season[i]) == bias_cell else 1.0 for i in test]
    pred = Predictions(
        row=test, competition=[comp[i] for i in test], season=[season[i] for i in test],
        lam_h=[th[i] * f for i, f in zip(test, factor, strict=True)],
        lam_a=[ta[i] * f for i, f in zip(test, factor, strict=True)],
        rho=[RHO] * len(test), share_h=[SHARE] * len(test), share_a=[SHARE] * len(test),
    )  # fmt: skip
    return hist, pred


def test_exact_engine_beats_naive_reference_without_alerts() -> None:
    hist, pred = _world(250, None, 3)
    report = calibration_report(goal_rows(hist, pred), dict(GOAL_GROUPS))
    ou = report["markets"]["OU|2.5|over"]
    assert ou["overall"]["n"] == 2 * 3 * 250
    assert ou["overall"]["skill"] > 0  # le moteur bat la fréquence du championnat
    assert set(ou["by_competition"]) == set(COMPS)
    assert set(ou["by_season"]) == {"2022", "2023", "2024"}
    assert abs(ou["overall"]["gap"]) < 3 * ou["overall"]["se"]
    assert sum(b["n"] for b in ou["curve"]) == ou["overall"]["n"]
    assert len(report["alerts"]) <= 1  # au plus une fausse alerte sur 102 cases


def test_biased_cell_is_flagged_and_located() -> None:
    hist, pred = _world(250, ("EPL", 2023), 3)
    report = calibration_report(goal_rows(hist, pred), dict(GOAL_GROUPS))
    flagged = {(a["market"], a["competition"], a["season"]) for a in report["alerts"]}
    assert ("+2,5 buts", "EPL", 2023) in flagged
    assert all((c, s) == ("EPL", 2023) for _, c, s in flagged)
    text = format_calibration(report)
    assert "Écart par championnat" in text
    assert "+2,5 buts — EPL 2023" in text
