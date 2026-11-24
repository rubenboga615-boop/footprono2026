"""Étude « mélange moteur + marché » (point 1 du testeur, 24/11/2026), étape 2 : analyse.

Entrée : le .npz de blend_predict.py (prévisions hors échantillon du moteur 1, cotes Pinnacle
d'ouverture et de clôture de football-data).

- Probabilité du marché sans marge : proportionnelle et Shin (méthode puissance en repère).
- Mélange linéaire p = w·p_marché + (1 − w)·p_moteur, w de 0 à 1 par pas de 0,01.
- Variante logit (log-linéaire) : p ∝ p_marché^a · p_moteur^b, a et b libres.
- w, a, b appris sur 2019-20 → 2021-22 (validation), mesurés sur 2022-23 → 2025-26 (test).
- Marché « avant-match » = cote d'ouverture de Pinnacle (football-data, relevée le vendredi
  pour le week-end) : c'est ce que l'application connaît quand elle compose un coupon. La
  clôture sert de repère et de prix pour le rendement.
- Écarts de log loss par match, ± 2 erreurs types (appariés).
- Coupons : chaque jour, 3 sélections de 1,20 à 1,70 (1X2, double chance, plus/moins 2,5),
  une par match, choisies par la plus forte probabilité de chaque source ; réussite et
  rendement aux cotes de clôture de Pinnacle.

    python blend_analyse.py blend.npz > sortie.txt
"""

import sys
from collections import defaultdict
from collections.abc import Callable
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import brentq, minimize

F = NDArray[np.float64]
VALIDATION = (2019, 2020, 2021)
TEST = (2022, 2023, 2024, 2025)
EPS = 1e-12


# --- marge retirée -----------------------------------------------------------------------


def proportional(odds: F) -> F:
    inv = 1 / odds
    return inv / inv.sum(axis=1, keepdims=True)


def _shin_one(q: F) -> F:
    total = q.sum()

    def probs(z: float) -> F:
        return (np.sqrt(z * z + 4 * (1 - z) * q * q / total) - z) / (2 * (1 - z))

    if total <= 1:
        return q / total
    z = brentq(lambda z: probs(z).sum() - 1, 0.0, 0.4)
    p = probs(z)
    return p / p.sum()


def shin(odds: F) -> F:
    return np.array([_shin_one(1 / row) for row in odds])


def _power_one(q: F) -> F:
    k = brentq(lambda k: (q**k).sum() - 1, 0.5, 3.0)
    return q**k


def power(odds: F) -> F:
    return np.array([_power_one(1 / row) for row in odds])


DEVIG: dict[str, Callable[[F], F]] = {"proportionnelle": proportional, "Shin": shin}


# --- mesures -----------------------------------------------------------------------------


def losses(p: F, y: NDArray[np.int64]) -> F:
    return -np.log(np.clip(p[np.arange(len(y)), y], EPS, 1))


def diff(a: F, b: F) -> str:
    d = a - b
    se = d.std(ddof=1) / np.sqrt(len(d))
    return f"{d.mean():+.4f} ± {2 * se:.4f}"


def linear(pm: F, pe: F, w: float) -> F:
    return w * pm + (1 - w) * pe


def loglinear(pm: F, pe: F, a: float, b: float) -> F:
    z = a * np.log(np.clip(pm, EPS, 1)) + b * np.log(np.clip(pe, EPS, 1))
    z -= z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def fit_w(pm: F, pe: F, y: NDArray[np.int64]) -> float:
    grid = np.round(np.arange(0, 1.0001, 0.01), 2)
    return float(grid[np.argmin([losses(linear(pm, pe, w), y).mean() for w in grid])])


def fit_ab(pm: F, pe: F, y: NDArray[np.int64]) -> tuple[float, float]:
    res = minimize(
        lambda v: losses(loglinear(pm, pe, v[0], v[1]), y).mean(), [1.0, 0.0], method="Nelder-Mead"
    )
    return float(res.x[0]), float(res.x[1])


def binary(p: F) -> F:
    return np.column_stack([p, 1 - p])


# --- lecture -----------------------------------------------------------------------------


def load(path: str) -> dict[str, Any]:
    d = dict(np.load(path))
    return d


def market_block(d: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Probabilités moteur, marché (ouverture, clôture) et issue pour un marché."""
    if name == "1X2":
        pe, y = d["model_1x2"], d["outcome_1x2"].astype(np.int64)
        pre, close = d["pre_1x2"], d["close_1x2"]
    elif name == "+/-2,5":
        pe = binary(d["model_ou25"])
        y = np.where(d["outcome_ou25"] == 1, 0, 1).astype(np.int64)
        pre, close = d["pre_ou25"], d["close_ou25"]
    else:
        return None
    ok = (
        np.all(np.isfinite(pre), axis=1)
        & np.all(np.isfinite(close), axis=1)
        & np.all(pre > 1, axis=1)
        & np.all(close > 1, axis=1)
        & (y >= 0)
    )
    return {"pe": pe[ok], "y": y[ok], "pre": pre[ok], "close": close[ok], "ok": ok}


def study(d: dict[str, Any], out: list[str]) -> dict[str, Any]:
    decisions: dict[str, Any] = {}
    seasons = d["season"]
    comps = d["competition"]
    for name in ("1X2", "+/-2,5"):
        b = market_block(d, name)
        assert b is not None
        ok = b["ok"]
        s, c = seasons[ok], comps[ok]
        val, test = np.isin(s, VALIDATION), np.isin(s, TEST)
        pe, y = b["pe"], b["y"]
        out.append(f"\n## {name} : {val.sum()} matchs de validation, {test.sum()} de test\n")
        close_p = power(b["close"])
        for dname, fn in DEVIG.items():
            pm = fn(b["pre"])
            w = fit_w(pm[val], pe[val], y[val])
            a, bb = fit_ab(pm[val], pe[val], y[val])
            lt = {
                "moteur": losses(pe[test], y[test]),
                "marché (ouverture)": losses(pm[test], y[test]),
                f"mélange w = {w:.2f}": losses(linear(pm, pe, w)[test], y[test]),
                f"logit a = {a:.2f}, b = {bb:.2f}": losses(
                    loglinear(pm, pe, a, bb)[test], y[test]
                ),
                "clôture (repère)": losses(close_p[test], y[test]),
            }
            out.append(f"### Marge retirée : {dname}\n")
            out.append("| Source | Log loss test | Écart avec le marché |")
            out.append("|---|---|---|")
            base = lt["marché (ouverture)"]
            for k, v in lt.items():
                out.append(f"| {k} | {v.mean():.4f} | {diff(v, base)} |")
            # Par championnat (w appris sur toute la validation)
            out.append("\nPar championnat (mélange − marché, test) :\n")
            out.append("| Championnat | Matchs | w | Mélange − marché | Moteur − marché |")
            out.append("|---|---|---|---|---|")
            blend = linear(pm, pe, w)
            for comp in sorted(set(c)):
                m = test & (c == comp)
                wc = fit_w(pm[val & (c == comp)], pe[val & (c == comp)], y[val & (c == comp)])
                bc = linear(pm, pe, wc)
                out.append(
                    f"| {comp} | {m.sum()} | {wc:.2f} | "
                    f"{diff(losses(bc[m], y[m]), losses(pm[m], y[m]))} | "
                    f"{diff(losses(pe[m], y[m]), losses(pm[m], y[m]))} |"
                )
            decisions[f"{name} {dname}"] = {
                "w": w,
                "a": a,
                "b": bb,
                "gain": float((losses(blend[test], y[test]) - base).mean()),
                "se": float(
                    (losses(blend[test], y[test]) - base).std(ddof=1) / np.sqrt(test.sum())
                ),
            }
            out.append("")
    return decisions


# --- coupons -----------------------------------------------------------------------------


def selections(d: dict[str, Any], source: str, w: float) -> list[tuple[str, int, float, float, int]]:
    """(jour, indice du match, probabilité de la source, cote de clôture, gagné)."""
    rows: list[tuple[str, int, float, float, int]] = []
    pre1, close1 = d["pre_1x2"], d["close_1x2"]
    pre_ou, close_ou = d["pre_ou25"], d["close_ou25"]
    y1, you = d["outcome_1x2"], d["outcome_ou25"]
    for i in range(len(y1)):
        if not (np.all(np.isfinite(pre1[i])) and np.all(np.isfinite(close1[i]))):
            continue
        if not (np.all(np.isfinite(pre_ou[i])) and np.all(np.isfinite(close_ou[i]))):
            continue
        pm1 = proportional(pre1[i : i + 1])[0]
        pmo = proportional(pre_ou[i : i + 1])[0]
        pe1, peo = d["model_1x2"][i], np.array([d["model_ou25"][i], 1 - d["model_ou25"][i]])
        if source == "moteur":
            p1, po = pe1, peo
        elif source == "marché":
            p1, po = pm1, pmo
        else:
            p1, po = linear(pm1[None], pe1[None], w)[0], linear(pmo[None], peo[None], w)[0]
        # Cote de clôture de la double chance : 1 / (1/a + 1/b) après retrait proportionnel
        # de la marge du 1X2 puis remise de la marge moyenne (approximation, Pinnacle ne la
        # cote pas chez football-data).
        q = 1 / close1[i]
        margin = q.sum()
        cands = [
            (p1[0], close1[i][0], int(y1[i] == 0)),
            (p1[1], close1[i][1], int(y1[i] == 1)),
            (p1[2], close1[i][2], int(y1[i] == 2)),
            (p1[0] + p1[1], 1 / ((q[0] + q[1]) / margin * np.sqrt(margin)), int(y1[i] != 2)),
            (p1[1] + p1[2], 1 / ((q[1] + q[2]) / margin * np.sqrt(margin)), int(y1[i] != 0)),
            (po[0], close_ou[i][0], int(you[i] == 1)),
            (po[1], close_ou[i][1], int(you[i] == 0)),
        ]
        best = max(
            (c for c in cands if 1.20 <= c[1] <= 1.70), key=lambda c: c[0], default=None
        )
        if best is not None:
            rows.append((str(d["date"][i]), i, float(best[0]), float(best[1]), best[2]))
    return rows


def coupons(d: dict[str, Any], w: float, out: list[str]) -> None:
    test = np.isin(d["season"], TEST)
    out.append("\n## Coupons de 3 sélections (1,20 à 1,70 chacune), saisons de test\n")
    out.append(
        "| Source | Sélections | Réussite | Rendement à la clôture | Coupons | Réussite "
        "| Rendement |"
    )
    out.append("|---|---|---|---|---|---|---|")
    for source in ("moteur", "marché", "mélange"):
        by_day: dict[str, list[tuple[float, float, int]]] = defaultdict(list)
        for day, i, p, odds, won in selections(d, source, w):
            if test[i]:
                by_day[day].append((p, odds, won))
        singles: list[tuple[float, int]] = []
        combos: list[tuple[float, int]] = []
        for picks in by_day.values():
            top = sorted(picks, key=lambda t: -t[0])[:3]
            singles += [(o, wn) for _, o, wn in top]
            if len(top) == 3:
                odds = float(np.prod([o for _, o, _ in top]))
                combos.append((odds, int(all(wn for _, _, wn in top))))
        for label, rows in (("", singles), ("c", combos)):
            r = np.array([o * wn - 1 for o, wn in rows])
            hit = np.mean([wn for _, wn in rows])
            if label == "":
                s_line = (
                    f"| {source} | {len(rows)} | {hit:.1%} | "
                    f"{r.mean():+.1%} ± {2 * r.std(ddof=1) / np.sqrt(len(r)):.1%} |"
                )
            else:
                out.append(
                    s_line + f" {len(rows)} | {hit:.1%} | "
                    f"{r.mean():+.1%} ± {2 * r.std(ddof=1) / np.sqrt(len(r)):.1%} |"
                )


def main(path: str) -> None:
    d = load(path)
    out: list[str] = [f"{len(d['season'])} matchs prédits hors échantillon"]
    dec = study(d, out)
    out.append("\n## Décision par marché (marge proportionnelle et Shin)\n")
    for k, v in dec.items():
        out.append(
            f"- {k} : w = {v['w']:.2f}, logit a = {v['a']:.2f} b = {v['b']:.2f}, "
            f"mélange − marché sur le test {v['gain']:+.4f} ± {2 * v['se']:.4f}"
        )
    coupons(d, dec["1X2 proportionnelle"]["w"], out)
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1])
