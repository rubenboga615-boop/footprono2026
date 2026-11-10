"""Chances pendant le match (engine/live.py)."""

import math

import pytest
from scipy.stats import poisson

from footprono.engine.live import ADDED, LiveState, live_markets, remaining

LAM = (1.6, 1.1, 0.45, 0.44)  # λ domicile, λ extérieur, part des buts en 1re période


def win(markets: dict, key: str) -> float:
    return markets[key].win


def test_remaining_time_by_period() -> None:
    assert remaining(LiveState("1H", 0, 0, 0, 0)) == (1.0, 1.0)
    r1, r2 = remaining(LiveState("1H", 30, 0, 0, 0))
    assert r1 == pytest.approx(1 - 30 / (45 + ADDED[0]))
    assert r2 == 1.0
    assert remaining(LiveState("HT", 45, 0, 1, 0)) == (0.0, 1.0)
    assert remaining(LiveState("2H", 90, 9, 1, 0)) == (0.0, 0.0)  # temps additionnel épuisé


def test_kick_off_matches_poisson_before_the_match() -> None:
    m = live_markets(*LAM, LiveState("1H", 0, 0, 0, 0), effect=(1.0,) * 5)
    assert m is not None
    # Sans but, sans minute jouée ni effet du score : la loi de Poisson d'avant-match.
    p00 = poisson.pmf(0, LAM[0]) * poisson.pmf(0, LAM[1])
    assert win(m, "OU|0.5|under") == pytest.approx(p00, abs=1e-6)
    total = sum(win(m, f"1X2||{s}") for s in ("home", "draw", "away"))
    assert total == pytest.approx(1.0)


def test_goals_already_scored_settle_markets() -> None:
    m = live_markets(*LAM, LiveState("1H", 30, 0, 1, 1))
    assert m is not None
    assert win(m, "OU|1.5|over") == pytest.approx(1.0)
    assert win(m, "BTTS||yes") == pytest.approx(1.0)
    assert win(m, "HT_OU|1.5|over") == pytest.approx(1.0)
    # Buts restants de la 1re période : 15 minutes et le temps additionnel sur 47.
    rate = (LAM[2] * LAM[0] + LAM[3] * LAM[1]) * (1 - 30 / (45 + ADDED[0]))
    plain = live_markets(*LAM, LiveState("1H", 30, 0, 1, 1), effect=(1.0,) * 5)
    assert plain is not None
    assert win(plain, "HT_OU|2.5|under") == pytest.approx(math.exp(-rate), abs=1e-6)


def test_half_time_keeps_the_score_and_the_whole_second_half() -> None:
    m = live_markets(*LAM, LiveState("HT", 45, 0, 2, 0))
    assert m is not None
    assert win(m, "HT_1X2||home") == pytest.approx(1.0)
    assert sum(win(m, f"1X2||{s}") for s in ("home", "draw", "away")) == pytest.approx(1.0)
    rate_away = (1 - LAM[3]) * LAM[1]
    rate_home = (1 - LAM[2]) * LAM[0]
    # Sans effet du score : P(nul) = Σ P(dom = k) · P(ext = k + 2) (Poisson), au pas d'une
    # minute près.
    draw = sum(poisson.pmf(k, rate_home) * poisson.pmf(k + 2, rate_away) for k in range(10))
    plain = live_markets(*LAM, LiveState("HT", 45, 0, 2, 0), effect=(1.0,) * 5)
    assert plain is not None
    assert win(plain, "1X2||draw") == pytest.approx(draw, abs=2e-3)


def test_second_half_uses_the_half_time_score() -> None:
    m = live_markets(*LAM, LiveState("2H", 70, 0, 1, 2, ht_home=0, ht_away=2))
    assert m is not None
    assert win(m, "HT_1X2||away") == pytest.approx(1.0)
    assert win(m, "1X2||away") > 0.6
    late = live_markets(*LAM, LiveState("2H", 90, 6, 1, 2, ht_home=0, ht_away=2))
    assert late is not None
    assert win(late, "1X2||away") == pytest.approx(1.0)


def test_no_chance_after_a_red_card_or_outside_regular_time() -> None:
    assert live_markets(*LAM, LiveState("2H", 60, 0, 0, 0, 0, 0, red_home=1)) is None
    assert live_markets(*LAM, LiveState("ET", 100, 0, 1, 1)) is None
    assert live_markets(*LAM, LiveState("FT", 90, 0, 1, 1)) is None


def test_score_effect_the_trailing_team_pushes() -> None:
    plain = live_markets(*LAM, LiveState("HT", 45, 0, 1, 0), effect=(1.0,) * 5)
    real = live_markets(*LAM, LiveState("HT", 45, 0, 1, 0))
    assert plain is not None
    assert real is not None
    # Menée d'un but à la pause, l'équipe à l'extérieur pousse : le domicile gagne moins.
    assert win(real, "1X2||home") < win(plain, "1X2||home")


def test_fit_score_effect_finds_a_known_effect() -> None:
    import numpy as np

    from footprono.engine.live import ADDED, GRID, HALF, evolve
    from footprono.engine.live_study import fit_score_effect

    rng = np.random.default_rng(3)
    truth = (1.0, 1.3, 1.0, 0.8, 1.0)
    rows = []
    for _ in range(3000):
        hht, aht = int(rng.integers(0, 3)), int(rng.integers(0, 3))
        start = np.zeros((GRID, GRID))
        start[hht, aht] = 1.0
        p = evolve(start, 0.8 / (HALF + ADDED[1]), 0.8 / (HALF + ADDED[1]), HALF + ADDED[1], truth)
        k = rng.choice(GRID * GRID, p=p.ravel() / p.sum())
        rows.append((1.6, 1.6, 0.5, 0.5, hht, aht, int(k // GRID), int(k % GRID)))
    fitted = fit_score_effect(rows)
    assert fitted[1] == pytest.approx(1.3, abs=0.2)
    assert fitted[3] == pytest.approx(0.8, abs=0.15)
