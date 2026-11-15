"""Moteur 3.0 : retrait de la marge et calage de la loi des scores sur la cote."""

import numpy as np
import pytest

from footprono.engine.market_fit import (
    MAX_FIT_ERROR,
    MarketTarget,
    fit_rates,
    power_devig,
)
from footprono.engine.scores import dixon_coles_matrix


def _probabilities(lam_h: float, lam_a: float, rho: float) -> tuple[float, float, float, float]:
    ft = dixon_coles_matrix(lam_h, lam_a, rho)
    h, a = np.indices(ft.shape)
    return (
        float(ft[h > a].sum()),
        float(ft[h == a].sum()),
        float(ft[h < a].sum()),
        float(ft[h + a > 2.5].sum()),
    )


def test_power_devig_sums_to_one_and_keeps_order() -> None:
    probs = power_devig([1.50, 4.20, 6.50])
    assert probs is not None
    assert sum(probs) == pytest.approx(1.0, abs=1e-9)
    assert probs[0] > probs[1] > probs[2]


def test_power_devig_removes_more_margin_from_outsiders() -> None:
    prices = [1.25, 6.00, 11.00]
    probs = power_devig(prices)
    assert probs is not None
    inv = [1 / p for p in prices]
    proportional = [x / sum(inv) for x in inv]
    # Favori : plus probable qu'avec la normalisation proportionnelle ; outsider : moins.
    assert probs[0] > proportional[0]
    assert probs[2] < proportional[2]


def test_power_devig_without_margin_returns_inverse_odds() -> None:
    assert power_devig([2.0, 2.0]) == pytest.approx([0.5, 0.5])


@pytest.mark.parametrize(
    "prices",
    [[1.9], [], [1.0, 3.0], [0.0, 2.0], [float("nan"), 2.0], [2.5, 2.5]],
)
def test_power_devig_refuses_unusable_markets(prices: list[float]) -> None:
    # Une seule issue, cote ≤ 1, valeur absente, ou somme des inverses < 1 (pas de marge).
    assert power_devig(prices) is None


@pytest.mark.parametrize(
    ("lam_h", "lam_a"), [(1.6, 1.1), (2.6, 0.6), (0.7, 1.9), (1.2, 1.2), (3.2, 0.5)]
)
def test_fit_recovers_rates_from_their_own_probabilities(lam_h: float, lam_a: float) -> None:
    rho = -0.06
    home, draw, away, over = _probabilities(lam_h, lam_a, rho)
    fit = fit_rates(MarketTarget(home, draw, away, 2.5, over), rho, start=(1.4, 1.2))
    assert fit is not None
    assert fit.lam_home == pytest.approx(lam_h, abs=0.01)
    assert fit.lam_away == pytest.approx(lam_a, abs=0.01)
    assert fit.error < 1e-3


def test_fit_without_total_keeps_engine_total_and_matches_1x2() -> None:
    rho = -0.05
    home, draw, away, _ = _probabilities(2.0, 0.9, rho)
    start = (1.5, 1.4)  # même total de buts (2,9), autre répartition
    fit = fit_rates(MarketTarget(home, draw, away), rho, start=start)
    assert fit is not None
    got = _probabilities(fit.lam_home, fit.lam_away, rho)
    assert got[0] == pytest.approx(home, abs=0.005)
    assert got[2] == pytest.approx(away, abs=0.005)
    assert fit.lam_home + fit.lam_away == pytest.approx(sum(start), abs=0.15)


def test_fit_moves_toward_the_market_not_the_engine() -> None:
    rho = -0.05
    # Le moteur voit un match équilibré, la cote un net favori à domicile.
    fit = fit_rates(MarketTarget(0.70, 0.19, 0.11, 2.5, 0.58), rho, start=(1.3, 1.3))
    assert fit is not None
    assert fit.lam_home > 2 * fit.lam_away
    assert fit.error <= MAX_FIT_ERROR


@pytest.mark.parametrize(
    "target",
    [
        MarketTarget(0.5, 0.3, 0.3),  # somme > 1
        MarketTarget(1.0, 0.0, 0.0),  # issue impossible
        MarketTarget(0.5, 0.25, 0.25, 2.5, 1.0),  # plus/moins impossible
    ],
)
def test_fit_refuses_incoherent_targets(target: MarketTarget) -> None:
    assert fit_rates(target, -0.05, start=(1.4, 1.2)) is None


def test_fit_refuses_when_markets_contradict_each_other() -> None:
    # Net favori (peu de nuls) mais presque aucun but attendu : aucune loi ne fait les deux.
    target = MarketTarget(0.80, 0.14, 0.06, 2.5, 0.05)
    assert fit_rates(target, -0.05, start=(1.4, 1.2)) is None
