"""Moteur de prédiction : cohérence des marchés, causalité, backtest (sans base)."""

from datetime import date, timedelta

import numpy as np
import pytest

from footprono.engine.backtest import BacktestConfig, run_backtest, summarize
from footprono.engine.goals import GoalsConfig, fit_goals
from footprono.engine.history import History
from footprono.engine.markets import AH_LINES, Selection, derive_markets
from footprono.engine.scores import dixon_coles_matrix, score_distribution
from footprono.ingestion.reference import AWARDED_MATCHES, load_teams

# --- Distribution des scores et marchés -----------------------------------------


def test_dixon_coles_matrix_is_a_distribution() -> None:
    m = dixon_coles_matrix(1.6, 1.1, -0.08)
    assert m.sum() == pytest.approx(1.0)
    assert (m >= 0).all()
    # rho = 0 : produit de deux lois de Poisson (normalisé).
    from scipy.stats import poisson

    g = np.arange(m.shape[0])
    ref = np.outer(poisson.pmf(g, 1.6), poisson.pmf(g, 1.1))
    assert dixon_coles_matrix(1.6, 1.1, 0.0) == pytest.approx(ref / ref.sum())


@pytest.fixture(scope="module")
def dist():  # type: ignore[no-untyped-def]
    return score_distribution(1.55, 1.05, -0.07, 0.44, 0.45)


def test_joint_distribution_is_consistent(dist) -> None:  # type: ignore[no-untyped-def]
    assert dist.joint.sum() == pytest.approx(1.0)
    # La marge « score final » est exactement la loi Dixon-Coles.
    assert dist.full_time == pytest.approx(dixon_coles_matrix(1.55, 1.05, -0.07), abs=1e-12)
    # Impossible de marquer moins sur le match qu'à la mi-temps.
    i, j, k, l_ = np.indices(dist.joint.shape)
    assert dist.joint[(k < i) | (l_ < j)].sum() == 0


def test_markets_are_mathematically_coherent(dist) -> None:  # type: ignore[no-untyped-def]
    m = derive_markets(dist)

    def w(key: str) -> float:
        return m[key].win

    home, draw, away = w("1X2||home"), w("1X2||draw"), w("1X2||away")
    assert home + draw + away == pytest.approx(1.0)
    assert w("DC||1X") == pytest.approx(home + draw)
    assert w("DC||X2") == pytest.approx(draw + away)
    for line in ("0.5", "1.5", "2.5", "3.5", "4.5", "5.5"):
        assert w(f"OU|{line}|over") + w(f"OU|{line}|under") == pytest.approx(1.0)
    assert w("OU|0.5|over") > w("OU|1.5|over") > w("OU|2.5|over") > w("OU|5.5|over")
    assert w("BTTS||yes") + w("BTTS||no") == pytest.approx(1.0)
    assert sum(s.win for k, s in m.items() if k.startswith("CS|")) == pytest.approx(1.0)
    # Combinés : la somme des cases redonne le marché simple.
    assert w("1X2_BTTS||home/yes") + w("1X2_BTTS||home/no") == pytest.approx(home)
    assert w("1X2_OU|2.5|draw/over") + w("1X2_OU|2.5|draw/under") == pytest.approx(draw)
    # Mi-temps / fin de match : marges égales aux marchés simples.
    htft = {k.split("|")[2]: s.win for k, s in m.items() if k.startswith("HTFT|")}
    assert sum(htft.values()) == pytest.approx(1.0)
    for res, p in (("home", home), ("draw", draw), ("away", away)):
        assert sum(v for k, v in htft.items() if k.endswith("/" + res)) == pytest.approx(p)
        ht = w(f"HT_1X2||{res}")
        assert sum(v for k, v in htft.items() if k.startswith(res + "/")) == pytest.approx(ht)
    assert sum(w(f"HIGHEST_HALF||{s}") for s in ("first", "second", "equal")) == pytest.approx(1.0)
    # Handicaps : AH 0 = remboursé si nul ; européen -1 = gagner par 2 buts ou plus.
    assert m["AH|0|home"] == Selection(win=home, push=draw)
    assert m["AH|0|home"] == m["DNB||home"]
    ah = m["AH|-0.25|home"]
    assert (ah.win, ah.half_loss) == pytest.approx((home, draw))
    assert w("EH|-1|home") == pytest.approx(w("MARGIN||home+2") + w("MARGIN||home+3"))
    for line in AH_LINES:
        s = m[f"AH|{line:g}|home"]
        assert s.win + s.half_win + s.push + s.half_loss + s.loss == pytest.approx(1.0)


def test_fair_odds() -> None:
    assert Selection(win=0.5).fair_odds == pytest.approx(2.0)
    # Remboursé si nul : 40 % gagné, 30 % remboursé, 30 % perdu → cote juste 1,75.
    assert Selection(win=0.4, push=0.3).fair_odds == pytest.approx(1.75)
    assert Selection(win=0.0).fair_odds is None


# --- Modèle des buts ------------------------------------------------------------


def synthetic_history(
    seed: int = 7, seasons: int = 4, n_teams: int = 12
) -> tuple[History, np.ndarray]:
    """Championnat fictif (tests uniquement) dont les forces réelles sont connues."""
    rng = np.random.default_rng(seed)
    strength = np.linspace(-0.45, 0.45, n_teams)
    rows = []
    for s in range(seasons):
        start = date(2016 + s, 8, 10)
        fixtures = [(h, a) for h in range(n_teams) for a in range(n_teams) if h != a]
        rng.shuffle(fixtures)
        for k, (h, a) in enumerate(fixtures):
            d = start + timedelta(days=2 * k // 6)
            lh = np.exp(0.25 + 0.25 + strength[h] - strength[a])
            la = np.exp(0.25 + strength[a] - strength[h])
            hg, ag = rng.poisson(lh), rng.poisson(la)
            rows.append(
                (2016 + s, d, h + 1, a + 1, hg, ag, rng.binomial(hg, 0.45), rng.binomial(ag, 0.45))
            )
    n = len(rows)
    hist = History(
        match_id=np.arange(1, n + 1, dtype=np.int64),
        competition=np.array(["TEST"] * n, dtype=np.str_),
        season=np.array([r[0] for r in rows], dtype=np.int64),
        date=np.array([np.datetime64(r[1], "D") for r in rows]),
        home=np.array([r[2] for r in rows], dtype=np.int64),
        away=np.array([r[3] for r in rows], dtype=np.int64),
        finished=np.ones(n, dtype=bool),
        excluded=np.zeros(n, dtype=bool),
        hg=np.array([r[4] for r in rows], dtype=np.float64),
        ag=np.array([r[5] for r in rows], dtype=np.float64),
        hht=np.array([r[6] for r in rows], dtype=np.float64),
        aht=np.array([r[7] for r in rows], dtype=np.float64),
        hxg=np.full(n, np.nan),
        axg=np.full(n, np.nan),
        odds={
            k: np.full((n, 3 if "1x2" in k else 2), np.nan)
            for k in ("pre_1x2", "close_1x2", "pre_ou25", "close_ou25")
        },
    )
    order = np.argsort(hist.date, kind="stable")
    return hist.subset(order), strength


def test_goals_model_recovers_team_strength() -> None:
    hist, strength = synthetic_history()
    as_of = hist.date.max() + np.timedelta64(1, "D")
    model = fit_goals(hist, "TEST", as_of, GoalsConfig(half_life_days=365, xg_weight=0))
    fitted = np.array(
        [model.team_params(t + 1)[0] - model.team_params(t + 1)[1] for t in range(len(strength))]
    )
    assert np.corrcoef(fitted, strength)[0, 1] > 0.9
    assert model.home_adv == pytest.approx(0.25, abs=0.12)
    assert 0.35 < model.ht_share_home < 0.55


def test_goals_model_ignores_the_future_and_excluded_matches() -> None:
    hist, _ = synthetic_history()
    as_of = np.datetime64("2018-01-15")
    cfg = GoalsConfig(half_life_days=365, xg_weight=0)
    reference = fit_goals(hist, "TEST", as_of, cfg)

    altered = hist.subset(np.ones(len(hist), dtype=bool))
    future = altered.date >= as_of
    altered.hg[future] = 9.0  # résultats du futur complètement changés
    altered.ag[future] = 0.0
    same = fit_goals(altered, "TEST", as_of, cfg)
    assert same.attack == pytest.approx(reference.attack)
    assert same.rho == pytest.approx(reference.rho)

    # Un match exclu (tapis vert) ne pèse pas, quel que soit son score.
    past = np.where(altered.date < as_of)[0][-1]
    altered.excluded[past] = True
    altered.hg[past] = 12.0
    without = fit_goals(altered, "TEST", as_of, cfg)
    altered.hg[past] = 0.0
    assert fit_goals(altered, "TEST", as_of, cfg).attack == pytest.approx(without.attack)


def test_goals_model_needs_history() -> None:
    hist, _ = synthetic_history()
    with pytest.raises(ValueError, match="trop peu de matchs"):
        fit_goals(hist, "TEST", hist.date.min() + np.timedelta64(3, "D"))


def test_backtest_beats_naive_reference_on_synthetic_league() -> None:
    hist, _ = synthetic_history(seasons=5)
    cfg = BacktestConfig(
        competitions=["TEST"],
        seasons=[2019, 2020],
        goals=GoalsConfig(half_life_days=365, xg_weight=0),
    )
    pred = run_backtest(hist, cfg)
    report = summarize(pred)
    assert report["n"] == len(pred.match_id) > 200
    assert report["1x2"]["model"]["log_loss"] < report["1x2"]["naive"]["log_loss"]
    # Aucune cote dans ce championnat fictif : comparaison au marché vide.
    assert report["1x2_vs_market"]["n"] == 0


def test_awarded_matches_use_reference_names() -> None:
    names = {(t.competition, t.name) for t in load_teams()}
    for comp, _season, home, away in AWARDED_MATCHES:
        assert (comp, home) in names
        assert (comp, away) in names


# --- Contexte et correction -----------------------------------------------------


def test_context_uses_only_previous_days() -> None:
    from footprono.engine.context import build_context

    hist, _ = synthetic_history(seasons=2)
    ctx = build_context(hist)
    first_day = hist.date == hist.date.min()
    assert (ctx.points[0][first_day] == 0).all()
    assert (ctx.progress[first_day] == 0).all()
    # Changer les résultats d'un jour ne change pas le contexte de ce jour-là.
    day = np.unique(hist.date)[40]
    altered = hist.subset(np.ones(len(hist), dtype=bool))
    altered.hg[altered.date >= day] = 7.0
    other = build_context(altered)
    same = hist.date <= day
    assert (other.points[0][same] == ctx.points[0][same]).all()
    for name in ctx.team:
        assert (other.team[name][0][same] == ctx.team[name][0][same]).all()
    # Classement : points cohérents avec les résultats de la saison.
    s0 = np.where(hist.season == hist.season.min())[0]
    last = s0[hist.date[s0] == hist.date[s0].max()][0]
    team = int(hist.home[last])
    before = s0[hist.date[s0] < hist.date[last]]
    pts = 0
    for i in before:
        for side, t in enumerate((hist.home[i], hist.away[i])):
            if t == team:
                gf, ga = (hist.hg[i], hist.ag[i]) if side == 0 else (hist.ag[i], hist.hg[i])
                pts += 3 if gf > ga else (1 if gf == ga else 0)
    assert ctx.points[0][last] == pts


def test_dead_rubber_detection() -> None:
    from footprono.engine.context import _enjeu, _Table

    teams = list(range(1, 21))
    table = _Table()
    for t in teams:
        table.played[t] = 36  # 2 journées restantes sur 38
        table.points[t] = 100 - 4 * t  # 4 points d'écart entre chaque place
    stakes = _enjeu(table, teams, 38, 36 / 38)
    # 10e : à 16 points du 6e et 28 du 17e → plus rien à jouer.
    assert stakes[10][0] == 1.0
    # 17e (dernier maintenu) : à 4 points du 18e, 2 matchs à jouer → enjeu.
    assert stakes[17] == (0.0, 0.0, 1.0)
    # En début de saison, personne n'est « sans enjeu ».
    early = _Table()
    for t in teams:
        early.played[t] = 5
        early.points[t] = 15 - (t % 5)
    assert all(v[0] == 0.0 for v in _enjeu(early, teams, 38, 0.1).values())


def test_correction_recovers_known_stretch_and_keeps_markets_coherent() -> None:
    from footprono.engine.context import MatchContext
    from footprono.engine.correction import fit_correction

    rng = np.random.default_rng(3)
    n = 20000
    lam_h, lam_a = rng.uniform(0.6, 2.4, n), rng.uniform(0.5, 2.0, n)
    dead_h = (rng.random(n) < 0.1).astype(float)
    d = np.log(lam_h) - np.log(lam_a)
    # Réalité : favoris plus forts que prévu (s = 0,1), équipe sans enjeu concède +20 %.
    true_h = lam_h * np.exp(0.1 * d)
    true_a = lam_a * np.exp(-0.1 * d + 0.2 * dead_h)
    ctx = MatchContext(progress=np.zeros(n), team={"dead": (dead_h, np.zeros(n))})
    rows = np.arange(n)
    corr = fit_correction(
        lam_h, lam_a, rng.poisson(true_h), rng.poisson(true_a), ctx, rows, ("dead",)
    )
    assert corr.coef["stretch"] == pytest.approx(0.1, abs=0.03)
    assert corr.coef["dead_concede"] == pytest.approx(0.2, abs=0.06)
    new_h, new_a = corr.apply(lam_h[:3], lam_a[:3], ctx, rows[:3])
    m = derive_markets(score_distribution(float(new_h[0]), float(new_a[0]), -0.05, 0.45, 0.45))
    assert sum(m[f"1X2||{r}"].win for r in ("home", "draw", "away")) == pytest.approx(1.0)


def test_corrected_backtest_is_causal() -> None:
    from footprono.engine.backtest import apply_correction
    from footprono.engine.context import build_context

    hist, _ = synthetic_history(seasons=5)
    cfg = BacktestConfig(["TEST"], [2017, 2018, 2019, 2020], GoalsConfig(365, xg_weight=0))
    pred = run_backtest(hist, cfg)
    out = apply_correction(hist, pred, build_context(hist), ("dead",))
    assert set(out.season) == {2019, 2020}
    # Changer les résultats de 2020 ne change pas les prévisions corrigées de 2019.
    altered = hist.subset(np.ones(len(hist), dtype=bool))
    altered.hg[altered.season == 2020] = 5.0
    pred2 = run_backtest(altered, cfg)
    out2 = apply_correction(altered, pred2, build_context(altered), ("dead",))
    keep = np.array(out.season) == 2019
    assert np.array(out2.model_1x2)[keep] == pytest.approx(np.array(out.model_1x2)[keep])
