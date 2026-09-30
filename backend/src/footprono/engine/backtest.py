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
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

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
    outcome_ht: list[int] = field(default_factory=list)
    ht_competition: list[str] = field(default_factory=list)
    market_close_1x2: list[FloatArray] = field(default_factory=list)
    market_pre_1x2: list[FloatArray] = field(default_factory=list)
    market_close_ou25: list[float] = field(default_factory=list)


def _result(h: float, a: float) -> int:
    return 0 if h > a else (1 if h == a else 2)


def _implied(odds: FloatArray) -> FloatArray:
    """Probabilités du marché : inverses des cotes, normalisées (marge retirée)."""
    if np.any(np.isnan(odds)) or np.any(odds <= 1):
        return np.full(len(odds), np.nan)
    inv = 1 / odds
    return np.asarray(inv / inv.sum(), dtype=np.float64)


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
            dist = score_distribution(
                lam_h, lam_a, model.rho, model.ht_share_home, model.ht_share_away
            )
            ft, ht = dist.full_time, dist.half_time
            h, a = np.indices(ft.shape)
            hh, ha = np.indices(ht.shape)
            p1x2 = np.array([ft[h > a].sum(), ft[h == a].sum(), ft[h < a].sum()])
            pht = np.array([ht[hh > ha].sum(), ht[hh == ha].sum(), ht[hh < ha].sum()])

            hg, ag = hist.hg[i], hist.ag[i]
            out.match_id.append(int(hist.match_id[i]))
            out.competition.append(comp)
            out.season.append(int(hist.season[i]))
            out.model_1x2.append(p1x2)
            out.naive_1x2.append(naive["1x2"])
            out.outcome_1x2.append(_result(hg, ag))
            out.model_ou25.append(float(ft[h + a > 2.5].sum()))
            out.naive_ou25.append(naive["ou25"])
            out.outcome_ou25.append(int(hg + ag > 2.5))
            out.model_btts.append(float(ft[(h > 0) & (a > 0)].sum()))
            out.naive_btts.append(naive["btts"])
            out.outcome_btts.append(int(hg > 0 and ag > 0))
            if not (np.isnan(hist.hht[i]) or np.isnan(hist.aht[i])):
                out.model_ht.append(pht)
                out.naive_ht.append(naive["ht"])
                out.outcome_ht.append(_result(hist.hht[i], hist.aht[i]))
                out.ht_competition.append(comp)
            out.market_close_1x2.append(_implied(hist.odds["close_1x2"][i]))
            out.market_pre_1x2.append(_implied(hist.odds["pre_1x2"][i]))
            close_ou = _implied(hist.odds["close_ou25"][i])
            out.market_close_ou25.append(float(close_ou[0]))
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
    hidx = np.array([competition is None or c == competition for c in pred.ht_competition])
    if hidx.any():
        yh = np.array(pred.outcome_ht)[hidx]
        report["ht_1x2"] = {
            "model": trio(np.array(pred.model_ht)[hidx], yh),
            "naive": trio(np.array(pred.naive_ht)[hidx], yh),
        }
    return report
