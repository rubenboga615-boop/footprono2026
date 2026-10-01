"""Couche de correction au-dessus de Dixon-Coles.

Le modèle des buts donne λ_dom et λ_ext. La correction les ajuste :

    log λ'_dom = log λ_dom + s·d + Σ_f (a_f·f_dom + b_f·f_ext)
    log λ'_ext = log λ_ext - s·d + Σ_f (a_f·f_ext + b_f·f_dom)

avec d = log λ_dom - log λ_ext (écart de niveau). ``s`` > 0 écarte les
favoris des outsiders : c'est la correction de calibration (le modèle brut est
un peu trop prudent sur les matchs déséquilibrés). ``f`` sont les indicateurs
de contexte retenus (``context.py``) : ``a_f`` agit sur l'attaque de l'équipe,
``b_f`` sur ce qu'elle concède.

Pas de constante ni d'avantage du terrain ici : le modèle des buts les
réestime chaque semaine ; une constante figée sur des saisons passées suivrait
mal les ruptures (saisons sans public 2020-21).

Les nouveaux λ' passent par la même loi des scores (rho et parts de
mi-temps inchangés) : tous les marchés restent cohérents entre eux.

Coefficients estimés par vraisemblance de Poisson sur les vrais buts, à
partir de prévisions **hors échantillon** (chaque λ a été prédit sans
connaître le match), avec une légère pénalité vers zéro.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize

from footprono.engine.context import MatchContext

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

RIDGE = 1.0
# Retenu sur les saisons de validation (docs/MOTEUR.md) : seul « sans enjeu »
# améliore les prévisions ; repos, forme, réussite et luttes n'apportent rien.
DEFAULT_FEATURES: tuple[str, ...] = ("dead",)


@dataclass(frozen=True)
class Correction:
    features: tuple[str, ...]
    coef: dict[str, float] = field(default_factory=dict)

    def apply(
        self, lam_h: FloatArray, lam_a: FloatArray, ctx: MatchContext, rows: IntArray
    ) -> tuple[FloatArray, FloatArray]:
        xh, xa, names = _design(lam_h, lam_a, ctx, rows, self.features)
        theta = np.array([self.coef.get(k, 0.0) for k in names])
        return lam_h * np.exp(xh @ theta), lam_a * np.exp(xa @ theta)


def _design(
    lam_h: FloatArray,
    lam_a: FloatArray,
    ctx: MatchContext,
    rows: IntArray,
    features: Sequence[str],
) -> tuple[FloatArray, FloatArray, list[str]]:
    d = np.log(lam_h) - np.log(lam_a)
    cols_h, cols_a, names = [d], [-d], ["stretch"]
    for f in features:
        fh, fa = ctx.team[f][0][rows], ctx.team[f][1][rows]
        cols_h += [fh, fa]
        cols_a += [fa, fh]
        names += [f"{f}_attack", f"{f}_concede"]
    return np.column_stack(cols_h), np.column_stack(cols_a), names


def fit_correction(
    lam_h: FloatArray,
    lam_a: FloatArray,
    hg: FloatArray,
    ag: FloatArray,
    ctx: MatchContext,
    rows: IntArray,
    features: Sequence[str] = (),
) -> Correction:
    xh, xa, names = _design(lam_h, lam_a, ctx, rows, features)
    x = np.vstack([xh, xa])
    base = np.log(np.concatenate([lam_h, lam_a]))
    y = np.concatenate([hg, ag])

    def nll(theta: FloatArray) -> tuple[float, FloatArray]:
        eta = base + x @ theta
        mu = np.exp(eta)
        value = float(np.sum(mu - y * eta) + 0.5 * RIDGE * theta @ theta)
        return value, x.T @ (mu - y) + RIDGE * theta

    res = minimize(nll, np.zeros(len(names)), jac=True, method="L-BFGS-B")
    return Correction(
        features=tuple(features), coef=dict(zip(names, map(float, res.x), strict=True))
    )
