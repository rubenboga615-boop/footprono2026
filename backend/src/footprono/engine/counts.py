"""Corners, cartons et tirs : modèle par équipe, sur le modèle des buts.

Pour chaque statistique (corners, cartons, tirs, tirs cadrés…) :

    log m_dom = μ + avantage_domicile + « pour »_dom + « contre »_ext
    log m_ext = μ + « pour »_ext + « contre »_dom

estimés par vraisemblance de Poisson pondérée dans le temps et pénalisée
(``goals.fit_ratings``), avec les seuls matchs joués avant la date de
prédiction. La dispersion (plus forte que Poisson pour les cartons) est
estimée par une loi binomiale négative commune au championnat.

Arbitre (cartons, fautes) : facteur multiplicatif = cartons observés dans ses
matchs / cartons attendus par le modèle, rétréci vers 1 tant qu'il a peu de
matchs (``referee_prior`` matchs fictifs « moyens »). Un arbitre inconnu a un
facteur 1.

Les marchés sortent de la loi du couple (domicile, extérieur), supposés
indépendants à moyennes données.
"""

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize_scalar
from scipy.special import gammaln
from scipy.stats import nbinom, poisson

from footprono.engine.goals import GoalsConfig, fit_ratings, training_mask
from footprono.engine.history import History
from footprono.engine.markets import Selection

FloatArray = NDArray[np.float64]

# Statistique modélisée -> colonnes de ``History.stats`` additionnées.
COUNT_STATS: dict[str, tuple[str, ...]] = {
    "corners": ("corners",),
    "cards": ("yellow_cards", "red_cards"),  # chaque carton compte pour 1
    "yellow_cards": ("yellow_cards",),
    "red_cards": ("red_cards",),
    "shots": ("shots",),
    "shots_on_target": ("shots_on_target",),
    "fouls": ("fouls",),
}
REFEREE_STATS = frozenset({"cards", "yellow_cards", "red_cards", "fouls"})
MAX_SIZE = 1000.0  # au-delà : loi de Poisson
MAX_COUNT = {"corners": 30, "shots": 60, "shots_on_target": 30, "fouls": 50}


@dataclass(frozen=True)
class CountsConfig:
    half_life_days: float = 180.0
    window_days: int = 3 * 365
    ridge: float = 30.0
    use_referee: bool = True
    referee_prior: float = 10.0


# Réglages choisis sur les saisons de validation 2019-20 → 2021-22 (docs/MOTEUR.md).
COUNTS_CONFIG: dict[str, CountsConfig] = {
    "corners": CountsConfig(ridge=60.0),
    "cards": CountsConfig(ridge=30.0),
    "shots": CountsConfig(ridge=60.0),
    "shots_on_target": CountsConfig(ridge=60.0),
}


def counts_config(stat: str) -> CountsConfig:
    return COUNTS_CONFIG.get(stat, CountsConfig())


@dataclass
class CountsModel:
    stat: str
    competition: str
    mu: float
    home_adv: float
    team_index: dict[int, int]
    attack: FloatArray
    defence: FloatArray
    size: float  # paramètre de la binomiale négative (MAX_SIZE = Poisson)
    referee_factor: dict[str, float] = field(default_factory=dict)
    n_matches: int = 0

    def means(self, home: int, away: int, referee: str = "") -> tuple[float, float]:
        kh, ka = self.team_index.get(home), self.team_index.get(away)
        ah, dh = (0.0, 0.0) if kh is None else (self.attack[kh], self.defence[kh])
        aa, da = (0.0, 0.0) if ka is None else (self.attack[ka], self.defence[ka])
        factor = self.referee_factor.get(referee, 1.0) if referee else 1.0
        mh = float(np.exp(self.mu + self.home_adv + ah + da)) * factor
        ma = float(np.exp(self.mu + aa + dh)) * factor
        return mh, ma

    def pmf(self, mean: float, max_count: int) -> FloatArray:
        k = np.arange(max_count + 1)
        if self.size >= MAX_SIZE:
            p = poisson.pmf(k, mean)
        else:
            p = nbinom.pmf(k, self.size, self.size / (self.size + mean))
        return np.asarray(p / p.sum(), dtype=np.float64)

    def joint(self, mh: float, ma: float) -> FloatArray:
        top = MAX_COUNT.get(self.stat, 20)
        return np.outer(self.pmf(mh, top), self.pmf(ma, top))


def count_values(hist: History, stat: str) -> tuple[FloatArray, FloatArray]:
    cols = COUNT_STATS[stat]
    yh = np.sum([hist.stats[c][0] for c in cols], axis=0)
    ya = np.sum([hist.stats[c][1] for c in cols], axis=0)
    return np.asarray(yh, dtype=np.float64), np.asarray(ya, dtype=np.float64)


def _nb_loglik(y: FloatArray, m: FloatArray, w: FloatArray, size: float) -> float:
    return float(
        np.sum(
            w
            * (
                gammaln(y + size)
                - gammaln(size)
                - gammaln(y + 1)
                + size * np.log(size / (size + m))
                + y * np.log(m / (size + m))
            )
        )
    )


def fit_counts(
    hist: History, competition: str, stat: str, as_of: np.datetime64, cfg: CountsConfig
) -> CountsModel:
    yh_all, ya_all = count_values(hist, stat)
    window = GoalsConfig(window_days=cfg.window_days)
    mask = training_mask(hist, competition, as_of, window) & ~np.isnan(yh_all) & ~np.isnan(ya_all)
    if mask.sum() < 50:
        raise ValueError(f"{competition} {stat} : trop peu de matchs avant {as_of}")
    h, a = hist.home[mask], hist.away[mask]
    yh, ya = yh_all[mask], ya_all[mask]
    w = 0.5 ** ((as_of - hist.date[mask]).astype(np.float64) / cfg.half_life_days)
    teams = np.unique(np.concatenate([h, a]))
    index = {int(t): k for k, t in enumerate(teams)}
    hi = np.array([index[int(t)] for t in h], dtype=np.int64)
    ai = np.array([index[int(t)] for t in a], dtype=np.int64)
    n = len(teams)
    zeros = np.zeros(n)
    theta = fit_ratings(hi, ai, yh, ya, w, n, cfg.ridge, zeros, zeros)
    mu, home = float(theta[0]), float(theta[1])
    att, dfn = theta[2 : 2 + n], theta[2 + n :]
    mh = np.exp(mu + home + att[hi] + dfn[ai])
    ma = np.exp(mu + att[ai] + dfn[hi])

    factors: dict[str, float] = {}
    if cfg.use_referee and stat in REFEREE_STATS and len(hist.referee):
        refs = hist.referee[mask]
        known = refs != ""
        if known.any():
            expected = mh + ma
            per_match = float(np.average(expected, weights=w))
            prior = cfg.referee_prior * per_match
            for ref in np.unique(refs[known]):
                sel = refs == ref
                obs = float(np.sum(w[sel] * (yh[sel] + ya[sel])))
                exp = float(np.sum(w[sel] * expected[sel]))
                factors[str(ref)] = (obs + prior) / (exp + prior)
            # Recalage des moyennes avant d'estimer la dispersion.
            f = np.array([factors.get(str(r), 1.0) for r in refs])
            mh, ma = mh * f, ma * f

    y = np.concatenate([yh, ya])
    m = np.concatenate([mh, ma])
    ww = np.concatenate([w, w])
    best = minimize_scalar(
        lambda log_s: -_nb_loglik(y, m, ww, float(np.exp(log_s))),
        bounds=(0.0, np.log(MAX_SIZE)),
        method="bounded",
    )
    size = float(np.exp(best.x))
    if size > 0.95 * MAX_SIZE:
        size = MAX_SIZE
    return CountsModel(
        stat=stat,
        competition=competition,
        mu=mu,
        home_adv=home,
        team_index=index,
        attack=att,
        defence=dfn,
        size=size,
        referee_factor=factors,
        n_matches=int(mask.sum()),
    )


# ------------------------------------------------------------------ marchés

TOTAL_LINES = {
    "corners": tuple(x + 0.5 for x in range(6, 14)),
    "cards": tuple(x + 0.5 for x in range(1, 8)),
    "shots": tuple(x + 0.5 for x in range(18, 31, 2)),
    "shots_on_target": tuple(x + 0.5 for x in range(5, 13)),
}
TEAM_LINES = {
    "corners": tuple(x + 0.5 for x in range(2, 8)),
    "cards": tuple(x + 0.5 for x in range(0, 4)),
    "shots": tuple(x + 0.5 for x in range(8, 17, 2)),
    "shots_on_target": tuple(x + 0.5 for x in range(2, 7)),
}
HANDICAP_LINES = (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5)
BOOKING_LINES = tuple(x + 0.5 for x in range(15, 75, 10))
MARKET_NAMES = {
    "corners": "CORNERS",
    "cards": "CARDS",
    "shots": "SHOTS",
    "shots_on_target": "SOT",
}


def count_markets(stat: str, joint: FloatArray) -> dict[str, Selection]:
    """Marchés d'une statistique à partir de la loi du couple (domicile, extérieur)."""
    name = MARKET_NAMES[stat]
    h, a = np.indices(joint.shape)
    total = h + a
    out: dict[str, Selection] = {}

    def put(market: str, line: str, sel: str, p: float) -> None:
        out[f"{market}|{line}|{sel}"] = Selection(win=float(p))

    for line in TOTAL_LINES[stat]:
        over = float(joint[total > line].sum())
        put(f"{name}_OU", f"{line:g}", "over", over)
        put(f"{name}_OU", f"{line:g}", "under", 1 - over)
    for side, values in (("HOME", h), ("AWAY", a)):
        for line in TEAM_LINES[stat]:
            over = float(joint[values > line].sum())
            put(f"{name}_TEAM_OU_{side}", f"{line:g}", "over", over)
            put(f"{name}_TEAM_OU_{side}", f"{line:g}", "under", 1 - over)
    put(f"{name}_1X2", "", "home", float(joint[h > a].sum()))
    put(f"{name}_1X2", "", "draw", float(joint[h == a].sum()))
    put(f"{name}_1X2", "", "away", float(joint[h < a].sum()))
    if stat == "corners":
        for line in HANDICAP_LINES:
            put("CORNERS_AH", f"{line:g}", "home", float(joint[h + line > a].sum()))
            put("CORNERS_AH", f"{line:g}", "away", float(joint[a - line > h].sum()))
    return out


def booking_points_markets(yellow: FloatArray, red: FloatArray) -> dict[str, Selection]:
    """Points de cartons (jaune 10, rouge 25) à partir des lois des totaux.

    ``yellow`` et ``red`` : lois du nombre total de cartons jaunes et rouges du
    match. Approximation : le 2e jaune suivi d'un rouge compte ici 10 + 25
    (selon les bookmakers il vaut 25 ou 35).
    """
    points: dict[int, float] = {}
    for y, py in enumerate(yellow):
        for r, pr in enumerate(red):
            v = 10 * y + 25 * r
            points[v] = points.get(v, 0.0) + float(py * pr)
    out = {}
    for line in BOOKING_LINES:
        over = sum(p for v, p in points.items() if v > line)
        out[f"BOOKING_POINTS_OU|{line:g}|over"] = Selection(win=over)
        out[f"BOOKING_POINTS_OU|{line:g}|under"] = Selection(win=1 - over)
    return out


def total_pmf(joint: FloatArray) -> FloatArray:
    """Loi du total (domicile + extérieur)."""
    h, a = np.indices(joint.shape)
    return np.asarray(np.bincount((h + a).ravel(), joint.ravel()), dtype=np.float64)
