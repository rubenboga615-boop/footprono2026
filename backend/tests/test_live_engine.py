"""Chances pendant le match (engine/live.py)."""

import math

import pytest
from scipy.stats import poisson

from footprono.engine.live import ADDED, LiveModel, LiveState, live_markets, remaining

FLAT = LiveModel(effect=(1.0,) * 5)  # rythme régulier, sans effet du score

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
    m = live_markets(*LAM, LiveState("1H", 0, 0, 0, 0), model=FLAT)
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
    plain = live_markets(*LAM, LiveState("1H", 30, 0, 1, 1), model=FLAT)
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
    plain = live_markets(*LAM, LiveState("HT", 45, 0, 2, 0), model=FLAT)
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
    plain = live_markets(*LAM, LiveState("HT", 45, 0, 1, 0), model=FLAT)
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


def test_half_time_angles_are_right_when_the_engine_is_right() -> None:
    import numpy as np

    from footprono.engine.live import ADDED, GRID, HALF, SCORE_EFFECT, evolve
    from footprono.engine.live_study import half_time_angles

    rng = np.random.default_rng(5)
    rows = []
    length = HALF + ADDED[1]
    for _ in range(1500):
        lh, la = float(rng.uniform(0.8, 2.2)), float(rng.uniform(0.6, 1.8))
        hht, aht = int(rng.poisson(0.45 * lh)), int(rng.poisson(0.45 * la))
        if max(hht, aht) > 6:
            continue
        start = np.zeros((GRID, GRID))
        start[hht, aht] = 1.0
        p = evolve(start, 0.55 * lh / length, 0.55 * la / length, length, SCORE_EFFECT)
        k = rng.choice(GRID * GRID, p=p.ravel() / p.sum())
        rows.append((lh, la, 0.45, 0.45, hht, aht, int(k // GRID), int(k % GRID)))
    rep = half_time_angles(rows)
    for name in ("Sûr", "Équilibré", "Audacieux"):
        s = rep[name]["selections"]
        assert abs(s["observed"] - s["announced"]) < 1.5 * s["two_se"] + 0.01, (name, s)
        assert rep[name]["coupons"]["n"] > 100


def test_fit_live_model_finds_a_known_rhythm_and_effect() -> None:
    import numpy as np

    from footprono.engine.live import ADDED, BUCKETS, HALF, phase_of
    from footprono.engine.live_study import PlayedMatch, fit_live_model, minute_entries, report

    rng = np.random.default_rng(11)
    first = tuple([0.8] * 6 + [1.0, 1.0, 1.3] + [1.4])
    second = tuple([0.9] * 6 + [1.0, 1.1, 1.3] + [1.5])
    # Effet du score plus fort en fin de match (l'équipe menée pousse) : 4 moments du match.
    truth = LiveModel(
        first=first,
        second=second,
        effect=(1.0, 1.05, 1.0, 0.95, 1.0) * 2 + (1.0, 1.25, 1.0, 0.85, 1.0) * 2,
    )
    matches = []
    for _ in range(4000):
        lh, la = float(rng.uniform(1.0, 2.0)), float(rng.uniform(0.8, 1.6))
        goals: list[tuple[int, int, str]] = []
        h = a = 0
        for half in (0, 1):
            weights = truth.first if half == 0 else truth.second
            length = HALF + ADDED[half]
            units = HALF + int(np.ceil(ADDED[half]))
            for unit in range(1, units + 1):
                bucket = BUCKETS if unit > HALF else (unit - 1) // 5
                for side, lam, mine, other in (("home", lh, h, a), ("away", la, a, h)):
                    phase = phase_of(half, unit)
                    eff = truth.effect_at(phase)[int(np.clip(mine - other, -2, 2)) + 2]
                    rate = 0.45 * lam / length * weights[bucket] * eff
                    if rng.random() < rate:
                        minute = unit if unit <= HALF else HALF
                        extra = 0 if unit <= HALF else unit - HALF
                        goals.append((minute + (0 if half == 0 else HALF), extra, side))
                        h, a = (h + 1, a) if side == "home" else (h, a + 1)
        first_half = [g for g in goals if g[0] <= HALF]
        hht = sum(g[2] == "home" for g in first_half)
        aht = len(first_half) - hht
        if max(h, a) > 10 or max(hht, aht) > 6:
            continue
        matches.append(PlayedMatch((lh, la, 0.45, 0.45), tuple(goals), (), (h, a, hht, aht)))
    fitted = fit_live_model(matches)
    # Fin de période plus riche en buts que le début, effet du score retrouvé.
    assert fitted.first[8] > fitted.first[0] + 0.25
    assert fitted.second[BUCKETS] > fitted.second[0] + 0.3
    late, early = fitted.effect_at(3), fitted.effect_at(1)
    assert late[1] == pytest.approx(1.25, abs=0.15)
    assert late[3] == pytest.approx(0.85, abs=0.12)
    assert late[1] > early[1]
    # Le modèle appris est juste sur ses propres matchs ; le rythme régulier moins.
    learned = {
        (r["checkpoint"], r["family"]): r
        for r in report(minute_entries(matches[:1500], fitted))["rows"]
    }
    assert learned[("75'", "Buts du match (plus/moins)")]["worst_gap"] < 0.03
    assert LiveModel.from_dict(fitted.as_dict()) == fitted
