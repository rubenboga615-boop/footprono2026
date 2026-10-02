"""Modèle des buts : Dixon-Coles pondéré dans le temps, par championnat.

Pour un match domicile contre extérieur :

    log λ_dom = μ + avantage_domicile + attaque_dom + défense_ext
    log λ_ext = μ + attaque_ext + défense_dom

(« défense » = tendance à encaisser). Les paramètres sont estimés par
vraisemblance de Poisson pondérée : un match joué il y a ``half_life_days``
jours pèse moitié moins qu'un match d'hier. Une pénalité ramène chaque équipe
vers un a priori (0, ou celui des promus pour une équipe sans historique dans
le championnat), ce qui stabilise les équipes qui ont peu joué.

Causalité (principe n° 3) : ``fit_goals(history, as_of)`` n'utilise que des
matchs joués **strictement avant** ``as_of``.

Option xG : la cible est un mélange ``(1 - xg_weight) * buts + xg_weight * xG``
(les xG mesurent mieux la qualité des occasions que les buts, plus bruités).
Le paramètre rho de Dixon-Coles (dépendance des petits scores) et la part des
buts marqués en première période sont estimés sur les vrais buts.
"""

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize, minimize_scalar

from footprono.engine.history import History, season_start

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class GoalsConfig:
    # Réglages choisis sur les saisons de validation 2019-20 → 2021-22
    # (jamais sur les saisons de test) : voir docs/MOTEUR.md.
    half_life_days: float = 180.0
    window_days: int = 3 * 365
    xg_weight: float = 0.7
    # Les xG Understat ont dérivé par rapport aux vrais buts (rapport buts/xG
    # passé de 1,00 en 2019-21 à 0,91 en 2025) : remis au niveau des vrais
    # buts du championnat sur la fenêtre (mêmes poids), ils ne gardent que
    # leur information relative (quelle équipe crée plus ou moins).
    xg_rescale: bool = True
    # Part des passes dangereuses (« deep » Understat, ramenées au niveau des xG)
    # dans le signal d'occasions : 0,3 choisi sur 2019-22, confirmé sur 2022-26
    # (1X2, plus/moins 2,5 et les deux marquent meilleurs ; docs/MOTEUR.md).
    deep_weight: float = 0.3
    ridge: float = 2.0
    # A priori des équipes sans historique dans la fenêtre (promus) :
    # moyenne du quart le plus faible des équipes du championnat.
    promoted_prior: bool = True


@dataclass
class GoalsModel:
    competition: str
    as_of: np.datetime64
    mu: float
    home_adv: float
    rho: float
    ht_share_home: float
    ht_share_away: float
    team_index: dict[int, int]
    attack: FloatArray
    defence: FloatArray
    prior_attack: float
    prior_defence: float
    n_matches: int
    config: GoalsConfig = field(default_factory=GoalsConfig)

    def team_params(self, team_id: int) -> tuple[float, float]:
        k = self.team_index.get(team_id)
        if k is None:
            return self.prior_attack, self.prior_defence
        return float(self.attack[k]), float(self.defence[k])

    def rates(self, home_id: int, away_id: int) -> tuple[float, float]:
        ah, dh = self.team_params(home_id)
        aa, da = self.team_params(away_id)
        lam_h = float(np.exp(self.mu + self.home_adv + ah + da))
        lam_a = float(np.exp(self.mu + aa + dh))
        return lam_h, lam_a


def _dc_log_tau(
    hg: FloatArray, ag: FloatArray, lh: FloatArray, la: FloatArray, rho: float
) -> FloatArray:
    tau = np.ones_like(lh)
    m00 = (hg == 0) & (ag == 0)
    m01 = (hg == 0) & (ag == 1)
    m10 = (hg == 1) & (ag == 0)
    m11 = (hg == 1) & (ag == 1)
    tau[m00] = 1 - lh[m00] * la[m00] * rho
    tau[m01] = 1 + lh[m01] * rho
    tau[m10] = 1 + la[m10] * rho
    tau[m11] = 1 - rho
    return np.log(np.clip(tau, 1e-10, None))


def fit_ratings(
    hi: NDArray[np.int64],
    ai: NDArray[np.int64],
    yh: FloatArray,
    ya: FloatArray,
    w: FloatArray,
    n: int,
    ridge: float,
    prior_att: FloatArray,
    prior_def: FloatArray,
) -> FloatArray:
    """Vraisemblance de Poisson pondérée, pénalisée vers un a priori.

    Renvoie ``[mu, domicile, attaque (n), défense (n)]``. Sert aux buts comme
    aux corners, cartons et tirs (``counts.py``).
    """

    def nll(theta: FloatArray) -> tuple[float, FloatArray]:
        mu, home = theta[0], theta[1]
        att, dfn = theta[2 : 2 + n], theta[2 + n :]
        lh = np.exp(mu + home + att[hi] + dfn[ai])
        la = np.exp(mu + att[ai] + dfn[hi])
        ll = np.sum(w * (yh * np.log(lh) - lh + ya * np.log(la) - la))
        pen = 0.5 * ridge * (np.sum((att - prior_att) ** 2) + np.sum((dfn - prior_def) ** 2))
        rh, ra = w * (lh - yh), w * (la - ya)
        g = np.empty_like(theta)
        g[0] = rh.sum() + ra.sum()
        g[1] = rh.sum()
        g[2 : 2 + n] = np.bincount(hi, rh, n) + np.bincount(ai, ra, n) + ridge * (att - prior_att)
        g[2 + n :] = np.bincount(ai, rh, n) + np.bincount(hi, ra, n) + ridge * (dfn - prior_def)
        return float(-ll + pen), g

    x0 = np.zeros(2 + 2 * n)
    x0[0] = np.log(max(np.average(yh + ya, weights=w) / 2, 0.1))
    res = minimize(nll, x0, jac=True, method="L-BFGS-B")
    return np.asarray(res.x, dtype=np.float64)


def training_mask(
    hist: History, competition: str, as_of: np.datetime64, cfg: GoalsConfig
) -> NDArray[np.bool_]:
    start = as_of - np.timedelta64(cfg.window_days, "D")
    mask = (
        (hist.competition == competition)
        & hist.finished
        & ~hist.excluded
        & (hist.date < as_of)
        & (hist.date >= start)
        & ~np.isnan(hist.hg)
        & ~np.isnan(hist.ag)
    )
    return np.asarray(mask, dtype=bool)


def _with_deep(
    hx: FloatArray, ax: FloatArray, hd: FloatArray, ad: FloatArray, w: FloatArray, weight: float
) -> tuple[FloatArray, FloatArray]:
    """xG mêlés aux passes dangereuses, ramenées au niveau des xG sur la fenêtre."""
    ok = ~np.isnan(hx) & ~np.isnan(ax) & ~np.isnan(hd) & ~np.isnan(ad)
    if not ok.any():
        return hx, ax
    k = float(np.sum(w[ok] * (hx[ok] + ax[ok])) / max(np.sum(w[ok] * (hd[ok] + ad[ok])), 1e-9))
    hx, ax = hx.copy(), ax.copy()
    hx[ok] = (1 - weight) * hx[ok] + weight * k * hd[ok]
    ax[ok] = (1 - weight) * ax[ok] + weight * k * ad[ok]
    return hx, ax


def fit_goals(
    hist: History, competition: str, as_of: np.datetime64, cfg: GoalsConfig | None = None
) -> GoalsModel:
    cfg = cfg or GoalsConfig()
    mask = training_mask(hist, competition, as_of, cfg)
    if mask.sum() < 50:
        raise ValueError(f"{competition} : trop peu de matchs avant {as_of} ({int(mask.sum())})")
    h, a = hist.home[mask], hist.away[mask]
    hg, ag = hist.hg[mask], hist.ag[mask]
    age = (as_of - hist.date[mask]).astype(np.float64)
    w = 0.5 ** (age / cfg.half_life_days)

    yh, ya = hg.copy(), ag.copy()
    if cfg.xg_weight > 0:
        hx, ax = hist.hxg[mask], hist.axg[mask]
        if cfg.deep_weight > 0 and len(hist.hdeep):
            hx, ax = _with_deep(hx, ax, hist.hdeep[mask], hist.adeep[mask], w, cfg.deep_weight)
        ok = ~np.isnan(hx) & ~np.isnan(ax)
        scale = 1.0
        if cfg.xg_rescale and ok.any():
            scale = float(
                np.sum(w[ok] * (hg[ok] + ag[ok])) / max(np.sum(w[ok] * (hx[ok] + ax[ok])), 1e-9)
            )
        yh[ok] = (1 - cfg.xg_weight) * hg[ok] + cfg.xg_weight * scale * hx[ok]
        ya[ok] = (1 - cfg.xg_weight) * ag[ok] + cfg.xg_weight * scale * ax[ok]

    teams = np.unique(np.concatenate([h, a]))
    index = {int(t): k for k, t in enumerate(teams)}
    hi = np.array([index[int(t)] for t in h], dtype=np.int64)
    ai = np.array([index[int(t)] for t in a], dtype=np.int64)
    n = len(teams)

    # Équipes sans match avant la saison en cours (promus) : a priori propre.
    current = season_start(int(str(as_of)[:4]) - (0 if int(str(as_of)[5:7]) >= 7 else 1))
    dates = hist.date[mask]
    seen_before = np.zeros(n, dtype=bool)
    before = dates < current
    seen_before[hi[before]] = True
    seen_before[ai[before]] = True
    newcomers = ~seen_before

    def solve(prior_att: FloatArray, prior_def: FloatArray) -> FloatArray:
        return fit_ratings(hi, ai, yh, ya, w, n, cfg.ridge, prior_att, prior_def)

    zeros = np.zeros(n)
    theta = solve(zeros, zeros)
    prior_att, prior_def = 0.0, 0.0
    if cfg.promoted_prior and newcomers.any() and (~newcomers).sum() >= 4:
        att, dfn = theta[2 : 2 + n], theta[2 + n :]
        strength = att - dfn
        established = np.where(~newcomers)[0]
        weakest = established[np.argsort(strength[established])[: max(1, len(established) // 4)]]
        prior_att, prior_def = float(att[weakest].mean()), float(dfn[weakest].mean())
        theta = solve(np.where(newcomers, prior_att, 0.0), np.where(newcomers, prior_def, 0.0))

    mu, home = float(theta[0]), float(theta[1])
    att, dfn = theta[2 : 2 + n], theta[2 + n :]
    lh = np.exp(mu + home + att[hi] + dfn[ai])
    la = np.exp(mu + att[ai] + dfn[hi])

    def rho_nll(rho: float) -> float:
        return float(-np.sum(w * _dc_log_tau(hg, ag, lh, la, rho)))

    rho = float(minimize_scalar(rho_nll, bounds=(-0.25, 0.25), method="bounded").x)

    hht, aht = hist.hht[mask], hist.aht[mask]
    ok = ~np.isnan(hht) & ~np.isnan(aht)
    share_h = float(np.sum(w[ok] * hht[ok]) / max(np.sum(w[ok] * hg[ok]), 1e-9))
    share_a = float(np.sum(w[ok] * aht[ok]) / max(np.sum(w[ok] * ag[ok]), 1e-9))

    return GoalsModel(
        competition=competition,
        as_of=as_of,
        mu=mu,
        home_adv=home,
        rho=rho,
        ht_share_home=float(np.clip(share_h, 0.3, 0.6)),
        ht_share_away=float(np.clip(share_a, 0.3, 0.6)),
        team_index=index,
        attack=att,
        defence=dfn,
        prior_attack=prior_att,
        prior_defence=prior_def,
        n_matches=int(mask.sum()),
        config=cfg,
    )
