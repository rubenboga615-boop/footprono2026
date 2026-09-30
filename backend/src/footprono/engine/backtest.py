"""Backtest strict dans le temps (principe n° 3).

Pour chaque championnat et chaque saison testée, le modèle est réestimé tous
les ``refit_every_days`` jours avec les seuls matchs joués **avant** la date de
réestimation, puis il prédit les matchs des jours suivants. Aucune information
postérieure au coup d'envoi n'est utilisée.

Trois prévisions sont comparées sur les mêmes matchs :
- **modèle** ;
- **référence naïve** : fréquences observées dans le championnat sur la fenêtre
  d'apprentissage (principe n° 6 : il faut la battre) ;
- **marché** : probabilités déduites des cotes (marge retirée par
  normalisation), à titre de repère seulement, jamais utilisées par le modèle.

Mesures : log loss (plus bas = mieux), score de Brier, RPS pour le 1X2
(tient compte de l'ordre domicile < nul < extérieur), et calibration.
"""

import itertools
from collections.abc import Sequence
from dataclasses import dataclass, field, fields
from typing import Any

import numpy as np
from numpy.typing import NDArray

from footprono.engine.context import MatchContext
from footprono.engine.correction import fit_correction
from footprono.engine.counts import (
    TOTAL_LINES,
    CountsConfig,
    count_values,
    fit_counts,
    total_pmf,
)
from footprono.engine.goals import GoalsConfig, fit_goals, training_mask
from footprono.engine.history import History
from footprono.engine.scores import score_distribution

FloatArray = NDArray[np.float64]
EPS = 1e-12


@dataclass(frozen=True)
class BacktestConfig:
    competitions: Sequence[str]
    seasons: Sequence[int]
    goals: GoalsConfig = field(default_factory=GoalsConfig)
    refit_every_days: int = 7


@dataclass
class Predictions:
    """Une ligne par match testé."""

    match_id: list[int] = field(default_factory=list)
    row: list[int] = field(default_factory=list)  # indice du match dans l'historique
    competition: list[str] = field(default_factory=list)
    season: list[int] = field(default_factory=list)
    model_1x2: list[FloatArray] = field(default_factory=list)
    naive_1x2: list[FloatArray] = field(default_factory=list)
    outcome_1x2: list[int] = field(default_factory=list)
    model_ou25: list[float] = field(default_factory=list)
    naive_ou25: list[float] = field(default_factory=list)
    outcome_ou25: list[int] = field(default_factory=list)
    model_btts: list[float] = field(default_factory=list)
    naive_btts: list[float] = field(default_factory=list)
    outcome_btts: list[int] = field(default_factory=list)
    model_ht: list[FloatArray] = field(default_factory=list)
    naive_ht: list[FloatArray] = field(default_factory=list)
    outcome_ht: list[int] = field(default_factory=list)  # -1 : score à la mi-temps absent
    market_close_1x2: list[FloatArray] = field(default_factory=list)
    market_pre_1x2: list[FloatArray] = field(default_factory=list)
    market_close_ou25: list[float] = field(default_factory=list)
    # Paramètres de la loi des scores, pour recalculer les marchés après correction.
    lam_h: list[float] = field(default_factory=list)
    lam_a: list[float] = field(default_factory=list)
    rho: list[float] = field(default_factory=list)
    share_h: list[float] = field(default_factory=list)
    share_a: list[float] = field(default_factory=list)

    def select(self, keep: NDArray[np.bool_]) -> "Predictions":
        out = Predictions()
        for f in fields(self):
            values = getattr(self, f.name)
            setattr(out, f.name, [v for v, k in zip(values, keep, strict=True) if k])
        return out


def _result(h: float, a: float) -> int:
    return 0 if h > a else (1 if h == a else 2)


def _implied(odds: FloatArray) -> FloatArray:
    """Probabilités du marché : inverses des cotes, normalisées (marge retirée)."""
    if np.any(np.isnan(odds)) or np.any(odds <= 1):
        return np.full(len(odds), np.nan)
    inv = 1 / odds
    return np.asarray(inv / inv.sum(), dtype=np.float64)


@dataclass(frozen=True)
class MatchProbabilities:
    p1x2: FloatArray
    ht_1x2: FloatArray
    ou25: float
    btts: float


def match_probabilities(
    lam_h: float, lam_a: float, rho: float, share_h: float, share_a: float
) -> MatchProbabilities:
    """Probabilités des marchés évalués, tirées de la même loi des scores."""
    dist = score_distribution(lam_h, lam_a, rho, share_h, share_a)
    ft, ht = dist.full_time, dist.half_time
    h, a = np.indices(ft.shape)
    hh, ha = np.indices(ht.shape)
    return MatchProbabilities(
        p1x2=np.array([ft[h > a].sum(), ft[h == a].sum(), ft[h < a].sum()]),
        ht_1x2=np.array([ht[hh > ha].sum(), ht[hh == ha].sum(), ht[hh < ha].sum()]),
        ou25=float(ft[h + a > 2.5].sum()),
        btts=float(ft[(h > 0) & (a > 0)].sum()),
    )


def run_backtest(hist: History, cfg: BacktestConfig) -> Predictions:
    out = Predictions()
    for comp in cfg.competitions:
        test = np.where(
            (hist.competition == comp)
            & np.isin(hist.season, list(cfg.seasons))
            & hist.finished
            & ~hist.excluded
            & ~np.isnan(hist.hg)
            & ~np.isnan(hist.ag)
        )[0]
        test = test[np.argsort(hist.date[test], kind="stable")]
        model = None
        fitted_on: np.datetime64 | None = None
        naive: dict[str, Any] = {}
        for i in test:
            day = hist.date[i]
            if fitted_on is None or day >= fitted_on + np.timedelta64(cfg.refit_every_days, "D"):
                model = fit_goals(hist, comp, day, cfg.goals)
                fitted_on = day
                naive = _naive_rates(hist, comp, day, cfg.goals)
            assert model is not None
            lam_h, lam_a = model.rates(int(hist.home[i]), int(hist.away[i]))
            probs = match_probabilities(
                lam_h, lam_a, model.rho, model.ht_share_home, model.ht_share_away
            )

            hg, ag = hist.hg[i], hist.ag[i]
            out.match_id.append(int(hist.match_id[i]))
            out.row.append(int(i))
            out.lam_h.append(lam_h)
            out.lam_a.append(lam_a)
            out.rho.append(model.rho)
            out.share_h.append(model.ht_share_home)
            out.share_a.append(model.ht_share_away)
            out.competition.append(comp)
            out.season.append(int(hist.season[i]))
            out.model_1x2.append(probs.p1x2)
            out.naive_1x2.append(naive["1x2"])
            out.outcome_1x2.append(_result(hg, ag))
            out.model_ou25.append(probs.ou25)
            out.naive_ou25.append(naive["ou25"])
            out.outcome_ou25.append(int(hg + ag > 2.5))
            out.model_btts.append(probs.btts)
            out.naive_btts.append(naive["btts"])
            out.outcome_btts.append(int(hg > 0 and ag > 0))
            out.model_ht.append(probs.ht_1x2)
            out.naive_ht.append(naive["ht"])
            has_ht = not (np.isnan(hist.hht[i]) or np.isnan(hist.aht[i]))
            out.outcome_ht.append(_result(hist.hht[i], hist.aht[i]) if has_ht else -1)
            out.market_close_1x2.append(_implied(hist.odds["close_1x2"][i]))
            out.market_pre_1x2.append(_implied(hist.odds["pre_1x2"][i]))
            close_ou = _implied(hist.odds["close_ou25"][i])
            out.market_close_ou25.append(float(close_ou[0]))
    return out


def apply_correction(
    hist: History,
    pred: Predictions,
    ctx: MatchContext,
    features: Sequence[str],
    min_train_seasons: int = 2,
) -> Predictions:
    """Corrige chaque saison avec une correction apprise sur les saisons précédentes.

    La correction de la saison S n'est estimée qu'avec les prévisions hors
    échantillon des saisons antérieures à S (causalité). Les saisons qui n'ont
    pas assez de saisons antérieures sont retirées.
    """
    season = np.array(pred.season)
    rows = np.array(pred.row, dtype=np.int64)
    lam_h, lam_a = np.array(pred.lam_h), np.array(pred.lam_a)
    first = season.min() + min_train_seasons
    out = pred.select(season >= first)
    out_season = np.array(out.season)
    for s in sorted(set(out.season)):
        train, target = season < s, season == s
        corr = fit_correction(
            lam_h[train], lam_a[train], hist.hg[rows[train]], hist.ag[rows[train]],
            ctx, rows[train], features,
        )  # fmt: skip
        new_h, new_a = corr.apply(lam_h[target], lam_a[target], ctx, rows[target])
        # Même ordre des matchs dans ``pred`` (saison == s) et dans ``out``.
        for k, lh, la in zip(np.where(out_season == s)[0], new_h, new_a, strict=True):
            probs = match_probabilities(
                float(lh), float(la), out.rho[k], out.share_h[k], out.share_a[k]
            )
            out.lam_h[k], out.lam_a[k] = float(lh), float(la)
            out.model_1x2[k], out.model_ht[k] = probs.p1x2, probs.ht_1x2
            out.model_ou25[k], out.model_btts[k] = probs.ou25, probs.btts
    return out


def _naive_rates(
    hist: History, comp: str, as_of: np.datetime64, cfg: GoalsConfig
) -> dict[str, Any]:
    m = training_mask(hist, comp, as_of, cfg)
    hg, ag = hist.hg[m], hist.ag[m]
    res = np.where(hg > ag, 0, np.where(hg == ag, 1, 2))
    ok = ~np.isnan(hist.hht[m]) & ~np.isnan(hist.aht[m])
    hh, ha = hist.hht[m][ok], hist.aht[m][ok]
    ht_res = np.where(hh > ha, 0, np.where(hh == ha, 1, 2))
    return {
        "1x2": np.bincount(res, minlength=3) / len(res),
        "ou25": float(np.mean(hg + ag > 2.5)),
        "btts": float(np.mean((hg > 0) & (ag > 0))),
        "ht": np.bincount(ht_res, minlength=3) / max(len(ht_res), 1),
    }


# Ligne de référence pour évaluer le plus/moins (proche de la médiane).
EVAL_LINE = {"corners": 9.5, "cards": 4.5, "shots": 24.5, "shots_on_target": 8.5}


def counts_backtest(
    hist: History,
    competitions: Sequence[str],
    seasons: Sequence[int],
    stat: str,
    cfg: CountsConfig,
    refit_every_days: int = 7,
) -> dict[str, Any]:
    """Évaluation stricte dans le temps d'une statistique (corners, cartons…).

    Référence naïve : distribution des totaux observée dans le championnat sur
    la fenêtre d'apprentissage. Mesures : log loss du total exact et du
    plus/moins à la ligne ``EVAL_LINE``.
    """
    yh, ya = count_values(hist, stat)
    line = EVAL_LINE.get(stat, TOTAL_LINES.get(stat, (0.5,))[0])
    model_total, naive_total, model_ou, naive_ou, outcome_ou = [], [], [], [], []
    for comp in competitions:
        test = np.where(
            (hist.competition == comp)
            & np.isin(hist.season, list(seasons))
            & hist.finished
            & ~hist.excluded
            & ~np.isnan(yh)
            & ~np.isnan(ya)
        )[0]
        test = test[np.argsort(hist.date[test], kind="stable")]
        fitted_on: np.datetime64 | None = None
        model = None
        naive = np.zeros(1)
        for i in test:
            day = hist.date[i]
            if fitted_on is None or day >= fitted_on + np.timedelta64(refit_every_days, "D"):
                model = fit_counts(hist, comp, stat, day, cfg)
                fitted_on = day
                m = training_mask(hist, comp, day, GoalsConfig(window_days=cfg.window_days))
                m &= ~np.isnan(yh) & ~np.isnan(ya)
                counts = np.bincount((yh[m] + ya[m]).astype(np.int64), minlength=120)
                naive = (counts + 0.5) / (counts + 0.5).sum()
            assert model is not None
            ref = str(hist.referee[i]) if len(hist.referee) else ""
            mh, ma = model.means(int(hist.home[i]), int(hist.away[i]), ref)
            pmf = total_pmf(model.joint(mh, ma))
            total = int(yh[i] + ya[i])
            model_total.append(pmf[total] if total < len(pmf) else EPS)
            naive_total.append(naive[total] if total < len(naive) else EPS)
            model_ou.append(float(pmf[np.arange(len(pmf)) > line].sum()))
            naive_ou.append(float(naive[np.arange(len(naive)) > line].sum()))
            outcome_ou.append(int(total > line))
    y = np.array(outcome_ou, dtype=np.int64)
    return {
        "stat": stat,
        "n": len(y),
        "line": line,
        "total_log_loss": {
            "model": float(-np.mean(np.log(np.clip(model_total, EPS, 1)))),
            "naive": float(-np.mean(np.log(np.clip(naive_total, EPS, 1)))),
        },
        "ou_log_loss": {
            "model": log_loss_binary(np.array(model_ou), y),
            "naive": log_loss_binary(np.array(naive_ou), y),
        },
        "ou_calibration": calibration_binary(np.array(model_ou), y),
    }


# ---------------------------------------------------------------- mesures


def log_loss_multi(p: FloatArray, y: NDArray[np.int64]) -> float:
    return float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], EPS, 1))))


def brier_multi(p: FloatArray, y: NDArray[np.int64]) -> float:
    onehot = np.eye(p.shape[1])[y]
    return float(np.mean(np.sum((p - onehot) ** 2, axis=1)))


def rps(p: FloatArray, y: NDArray[np.int64]) -> float:
    onehot = np.eye(p.shape[1])[y]
    cp, co = np.cumsum(p, axis=1)[:, :-1], np.cumsum(onehot, axis=1)[:, :-1]
    return float(np.mean(np.sum((cp - co) ** 2, axis=1) / (p.shape[1] - 1)))


def log_loss_binary(p: FloatArray, y: NDArray[np.int64]) -> float:
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier_binary(p: FloatArray, y: NDArray[np.int64]) -> float:
    return float(np.mean((p - y) ** 2))


def calibration(p: FloatArray, y: NDArray[np.int64], bins: int = 10) -> list[dict[str, float]]:
    """Probabilité annoncée contre fréquence observée, toutes issues 1X2 confondues."""
    probs = p.ravel()
    hits = np.eye(p.shape[1])[y].ravel()
    edges = np.linspace(0, 1, bins + 1)
    rows = []
    for lo, hi in itertools.pairwise(edges):
        sel = (probs >= lo) & (probs < hi) if hi < 1 else (probs >= lo) & (probs <= hi)
        if sel.sum() >= 20:
            rows.append(
                {
                    "from": float(lo),
                    "to": float(hi),
                    "n": int(sel.sum()),
                    "announced": float(probs[sel].mean()),
                    "observed": float(hits[sel].mean()),
                }
            )
    return rows


def calibration_binary(
    p: FloatArray, y: NDArray[np.int64], bins: int = 10
) -> list[dict[str, float]]:
    edges = np.linspace(0, 1, bins + 1)
    rows = []
    for lo, hi in itertools.pairwise(edges):
        sel = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        if sel.sum() >= 20:
            rows.append(
                {
                    "from": float(lo),
                    "to": float(hi),
                    "n": int(sel.sum()),
                    "announced": float(p[sel].mean()),
                    "observed": float(y[sel].mean()),
                }
            )
    return rows


def summarize(pred: Predictions, competition: str | None = None) -> dict[str, Any]:
    idx = np.array([competition is None or c == competition for c in pred.competition])
    if not idx.any():
        return {"n": 0}
    y = np.array(pred.outcome_1x2)[idx]
    model = np.array(pred.model_1x2)[idx]
    naive = np.array(pred.naive_1x2)[idx]
    close = np.array(pred.market_close_1x2)[idx]
    has_close = ~np.isnan(close).any(axis=1)
    yo = np.array(pred.outcome_ou25)[idx]
    mo, no = np.array(pred.model_ou25)[idx], np.array(pred.naive_ou25)[idx]
    co = np.array(pred.market_close_ou25)[idx]
    has_co = ~np.isnan(co)
    yb = np.array(pred.outcome_btts)[idx]
    mb, nb = np.array(pred.model_btts)[idx], np.array(pred.naive_btts)[idx]

    def trio(p: FloatArray, yy: NDArray[np.int64]) -> dict[str, float]:
        return {"log_loss": log_loss_multi(p, yy), "brier": brier_multi(p, yy), "rps": rps(p, yy)}

    report: dict[str, Any] = {
        "n": int(idx.sum()),
        "1x2": {"model": trio(model, y), "naive": trio(naive, y)},
        "1x2_vs_market": {
            "n": int(has_close.sum()),
            "model": trio(model[has_close], y[has_close]) if has_close.any() else None,
            "market_close": trio(close[has_close], y[has_close]) if has_close.any() else None,
        },
        "ou25": {
            "model": {"log_loss": log_loss_binary(mo, yo), "brier": brier_binary(mo, yo)},
            "naive": {"log_loss": log_loss_binary(no, yo), "brier": brier_binary(no, yo)},
            "vs_market": {
                "n": int(has_co.sum()),
                "model": log_loss_binary(mo[has_co], yo[has_co]) if has_co.any() else None,
                "market_close": log_loss_binary(co[has_co], yo[has_co]) if has_co.any() else None,
            },
        },
        "btts": {
            "model": {"log_loss": log_loss_binary(mb, yb), "brier": brier_binary(mb, yb)},
            "naive": {"log_loss": log_loss_binary(nb, yb), "brier": brier_binary(nb, yb)},
        },
        "calibration_1x2": calibration(model, y),
    }
    yh = np.array(pred.outcome_ht)[idx]
    hidx = yh >= 0
    if hidx.any():
        report["ht_1x2"] = {
            "model": trio(np.array(pred.model_ht)[idx][hidx], yh[hidx]),
            "naive": trio(np.array(pred.naive_ht)[idx][hidx], yh[hidx]),
        }
    return report
