"""Étude « angle du match » : règlement exact et détection de la malédiction du gagnant."""

import numpy as np

from footprono.engine.angles import angles_study, format_report, match_selections
from footprono.engine.backtest import Predictions
from footprono.engine.history import History
from footprono.engine.scores import score_distribution

SHARE = 0.44
RHO = -0.05


def _world(n: int, noise: float, seed: int) -> tuple[History, Predictions]:
    """Scores tirés de la vraie loi ; le « moteur » voit des buts attendus bruités."""
    rng = np.random.default_rng(seed)
    true_h = rng.uniform(0.6, 2.6, n)
    true_a = rng.uniform(0.4, 1.9, n)
    hg, ag, hht, aht = (np.zeros(n) for _ in range(4))
    for i in range(n):
        joint = score_distribution(true_h[i], true_a[i], RHO, SHARE, SHARE).joint
        flat = rng.choice(joint.size, p=joint.ravel() / joint.sum())
        hht[i], aht[i], hg[i], ag[i] = np.unravel_index(flat, joint.shape)
    days = np.datetime64("2024-08-01") + (np.arange(n) // 8).astype("timedelta64[D]")
    hist = History(
        match_id=np.arange(n), competition=np.full(n, "EPL"), season=np.full(n, 2024),
        date=days, home=np.zeros(n, dtype=np.int64), away=np.ones(n, dtype=np.int64),
        finished=np.ones(n, dtype=bool), excluded=np.zeros(n, dtype=bool),
        hg=hg, ag=ag, hht=hht, aht=aht, hxg=np.full(n, np.nan), axg=np.full(n, np.nan),
        odds={"close_1x2": np.full((n, 3), np.nan), "close_ou25": np.full((n, 2), np.nan)},
    )  # fmt: skip
    factor_h = np.exp(rng.normal(0, noise, n)) if noise else np.ones(n)
    factor_a = np.exp(rng.normal(0, noise, n)) if noise else np.ones(n)
    pred = Predictions(
        row=list(range(n)), lam_h=list(true_h * factor_h), lam_a=list(true_a * factor_a),
        rho=[RHO] * n, share_h=[SHARE] * n, share_a=[SHARE] * n,
    )  # fmt: skip
    return hist, pred


def test_selections_are_settled_with_the_real_score() -> None:
    hist, pred = _world(1, 0.0, 1)
    hist.hg[0], hist.ag[0], hist.hht[0], hist.aht[0] = 2, 1, 1, 0
    won = {key: w for key, _, w in match_selections(hist, pred, 0)}
    expected = {
        "1X2||home": True, "1X2||draw": False, "OU|2.5|over": True, "OU|3.5|over": False,
        "BTTS||yes": True, "HT_1X2||home": True, "HT_OU|0.5|over": True,
        "DC||1X": True, "DC||X2": False,
    }  # fmt: skip
    assert {k: won[k] for k in expected} == expected
    assert not any(key.startswith(("CS|", "AH|", "DNB|")) for key in won)  # exclus
    # Mi-temps inconnue : aucun marché de mi-temps.
    hist.hht[0] = np.nan
    assert not any(k.startswith("HT_") for k, _, _ in match_selections(hist, pred, 0))


def test_perfect_engine_keeps_its_promise() -> None:
    hist, pred = _world(2500, 0.0, 7)
    report = angles_study(hist, pred)
    for prof in report["profiles"].values():
        angle = prof["angle"]
        assert abs(angle["gap"]) <= 1.5 * angle["two_se"], angle


def test_noisy_engine_is_caught_overestimating_its_best_angle() -> None:
    hist, pred = _world(2500, 0.45, 7)
    report = angles_study(hist, pred)
    sure = report["profiles"]["sûr"]["angle"]
    assert sure["gap"] < -sure["two_se"], sure
    text = format_report(report)
    assert "Profil « sûr »" in text
    assert "coupons du jour" in text
