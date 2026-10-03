"""Niveaux de données : réglages par championnat, xG tirés des tirs, profil de buts."""

import numpy as np

from footprono.engine.goals import GoalsConfig, GoalsModel
from footprono.engine.history import History
from footprono.engine.tiers import (
    SHOT_XG,
    SHOT_XG_STRETCH,
    apply_shot_xg,
    goals_config,
    market_allowed,
    tier,
)


def test_settings_by_level() -> None:
    assert tier("EPL").level == 1
    assert goals_config("EPL") == GoalsConfig()  # niveau 1 inchangé
    custom = GoalsConfig(half_life_days=90.0)
    assert goals_config("LIGUE_1", custom) is custom
    por = goals_config("POR", custom)  # niveau 2 : ses propres réglages
    assert (por.xg_weight, por.deep_weight, por.half_life_days, por.profile_shrink) == (
        0.5,
        0.0,
        365.0,
        0.5,
    )
    for code in ("NED", "GRE", "TUR"):
        assert tier(code).level == 2
    assert not tier("BEL").correction
    assert not tier("BEL").counts


def test_btts_withdrawn_at_level_2_only() -> None:
    for key in ("BTTS||yes", "1X2_BTTS||home/yes", "OU_BTTS|2.5|over/no"):
        assert not market_allowed("POR", key)
        assert market_allowed("EPL", key)
    assert market_allowed("BEL", "1X2||home")
    assert market_allowed("BEL", "OU|2.5|over")


def _hist(
    comps: list[str], shots: list[tuple[float, float, float, float, float, float]]
) -> History:
    n = len(comps)
    col = lambda k: np.array([s[k] for s in shots], dtype=np.float64)  # noqa: E731
    return History(
        match_id=np.arange(1, n + 1, dtype=np.int64),
        competition=np.array(comps, dtype=np.str_),
        season=np.full(n, 2024, dtype=np.int64),
        date=np.array([np.datetime64("2024-09-01", "D")] * n),
        home=np.arange(1, n + 1, dtype=np.int64),
        away=np.arange(101, 101 + n, dtype=np.int64),
        finished=np.ones(n, dtype=bool),
        excluded=np.zeros(n, dtype=bool),
        hg=np.ones(n), ag=np.ones(n), hht=np.zeros(n), aht=np.zeros(n),
        hxg=np.full(n, np.nan), axg=np.full(n, np.nan),
        stats={
            "shots": (col(0), col(1)),
            "shots_on_target": (col(2), col(3)),
            "corners": (col(4), col(5)),
        },
    )  # fmt: skip


def test_shot_xg_only_for_level_2_and_stretched() -> None:
    nan = float("nan")
    hist = _hist(
        ["POR", "POR", "POR", "EPL"],
        [
            (10, 8, 4, 3, 5, 4),
            (20, 6, 8, 2, 7, 3),
            (nan, nan, nan, nan, nan, nan),
            (15, 9, 5, 3, 6, 5),
        ],
    )
    apply_shot_xg(hist)
    b0, on, off, corner = SHOT_XG
    raw_home = [b0 + on * 4 + off * 6 + corner * 5, b0 + on * 8 + off * 12 + corner * 7]
    mean = np.mean(raw_home)
    expected = [mean + SHOT_XG_STRETCH * (x - mean) for x in raw_home]
    assert np.allclose(hist.hxg[:2], expected)
    assert np.isnan(hist.hxg[2])  # pas de tirs : les vrais buts serviront
    assert np.isnan(hist.hxg[3])  # niveau 1 : jamais de xG « maison »


def test_profile_shrink_keeps_strength() -> None:
    def model(shrink: float) -> GoalsModel:
        return GoalsModel(
            competition="POR", as_of=np.datetime64("2024-09-01"), mu=0.1, home_adv=0.2, rho=-0.05,
            ht_share_home=0.45, ht_share_away=0.45, team_index={1: 0, 2: 1, 3: 2},
            attack=np.array([0.4, -0.1, -0.3]), defence=np.array([0.2, 0.0, -0.2]),
            prior_attack=-0.2, prior_defence=0.1, n_matches=300,
            config=GoalsConfig(profile_shrink=shrink),
        )  # fmt: skip

    full, half = model(1.0), model(0.5)
    mean = float(np.mean(full.attack + full.defence))
    for team in (1, 2, 3, 99):  # 99 : promu, a priori du championnat
        a1, d1 = full.team_params(team)
        a2, d2 = half.team_params(team)
        assert np.isclose(a1 - d1, a2 - d2)  # force inchangée
        assert np.isclose(a2 + d2 - mean, 0.5 * (a1 + d1 - mean))  # profil à mi-chemin
    # Le favori reste le favori.
    lh1, la1 = full.rates(1, 3)
    lh2, la2 = half.rates(1, 3)
    assert (lh1 > la1) == (lh2 > la2)


def test_reliability_backtest_matches_data_level() -> None:
    from footprono.predictions.reliability import BACKTEST, BACKTEST_LEVEL_2, backtest_for

    assert backtest_for(None) is BACKTEST
    assert backtest_for("EPL") is BACKTEST
    assert backtest_for("por") is BACKTEST_LEVEL_2
    assert "BTTS" not in BACKTEST_LEVEL_2["log_loss"]  # pas d'avis du moteur à ce niveau
