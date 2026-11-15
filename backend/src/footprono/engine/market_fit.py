"""Moteur 3.0 : modèle des scores calé sur la cote de référence.

Mesuré le 15/11/2026 (docs/ETUDE_MOTEUR_V3_2026-11-15.md) :

- face à la cote d'avant-match, le modèle des buts seul ne pèse rien sur le 1-N-2 ni sur le
  plus/moins (poids appris 0,00 à 0,06 sur 25 000 matchs) ;
- en revanche, si l'on **cale** (λ domicile, λ extérieur) pour que la loi des scores
  reproduise le 1-N-2 et le plus/moins 2,5 de la cote, marge retirée, tout en gardant du
  moteur rho et les parts de mi-temps, la loi obtenue prédit mieux que le moteur les marchés
  qui n'ont **pas** servi au calage : « les deux équipes marquent » -0,0027 ± 0,0012 de
  log loss, résultat à la mi-temps -0,0066 ± 0,0017 (15 019 matchs 2022-2026 ; mêmes
  écarts sur 2019-2021).

Tous les marchés continuent de sortir d'une seule loi des scores (principe n° 5). Le
modèle des buts reste estimé sans aucune cote (``goals.py``) : il fournit le point de
départ, rho, les parts de mi-temps, et sert seul quand aucune cote de référence n'existe.

La marge est retirée par la méthode puissance (p = (1 / cote)^k, somme = 1) : elle retire
plus de marge aux outsiders qu'aux favoris, comme le font les bookmakers (log loss 0,9547
contre 0,9561 pour la normalisation proportionnelle, calibration meilleure aux extrêmes).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq, minimize

from footprono.engine.scores import dixon_coles_matrix

# Écart maximal toléré entre la loi calée et la cote (en probabilité) : au-delà, le calage
# est refusé et le moteur seul est gardé (cotes incohérentes entre elles, erreur de saisie).
# Trois contraintes (1, 2, plus/moins) pour deux inconnues : un écart reste presque toujours
# (médiane 0,006, 99 % sous 0,022 sur 25 458 matchs) et le calage améliore les prévisions
# dans toutes les tranches d'écart jusqu'à 0,05 ; 0,05 % des matchs dépassent 0,03.
MAX_FIT_ERROR = 0.03
_EPS = 1e-6
_LAMBDA_BOUNDS = (0.05, 6.0)


def power_devig(prices: Sequence[float]) -> list[float] | None:
    """Probabilités d'un marché complet (issues exclusives), marge retirée.

    ``None`` si les cotes ne forment pas un marché exploitable : moins de deux issues, cote
    ≤ 1, ou somme des inverses inférieure à 1 (pas de marge : relevés de moments différents).
    """
    if len(prices) < 2 or any(not np.isfinite(p) or p <= 1 for p in prices):
        return None
    inv = np.array([1 / p for p in prices], dtype=np.float64)
    if inv.sum() < 1:
        return None
    if inv.sum() - 1 < 1e-12:
        return [float(x) for x in inv]
    k = brentq(lambda z: float((inv**z).sum()) - 1, 1.0, 50.0)
    return [float(x) for x in inv**k]


@dataclass(frozen=True)
class MarketTarget:
    """Ce que dit la cote de référence, marge retirée."""

    home: float
    draw: float
    away: float
    # Plus/moins : ligne (demi-entière) et probabilité du « plus » ; absent si non coté.
    line: float | None = None
    over: float | None = None


@dataclass(frozen=True)
class Fit:
    lam_home: float
    lam_away: float
    error: float  # plus grand écart de probabilité entre la loi calée et la cible


def _logit(p: float) -> float:
    p = min(max(p, _EPS), 1 - _EPS)
    return float(np.log(p / (1 - p)))


def _outcomes(lam_h: float, lam_a: float, rho: float, line: float | None) -> tuple[float, ...]:
    ft = dixon_coles_matrix(lam_h, lam_a, rho)
    home, away = float(np.tril(ft, -1).sum()), float(np.triu(ft, 1).sum())
    if line is None:
        return home, away
    h, a = np.indices(ft.shape)
    return home, away, float(ft[h + a > line].sum())


def fit_rates(target: MarketTarget, rho: float, start: tuple[float, float]) -> Fit | None:
    """(λ domicile, λ extérieur) dont la loi Dixon-Coles reproduit la cible.

    Avec le plus/moins : trois contraintes pour deux inconnues, ajustées au mieux (moindres
    carrés en logit). Sans : le 1-N-2 fixe l'écart entre les équipes, et le total de buts
    reste celui du moteur (``start``). ``None`` si la cible est incohérente ou si l'écart
    restant dépasse ``MAX_FIT_ERROR``.
    """
    probs = (target.home, target.draw, target.away)
    if any(not _EPS < p < 1 for p in probs) or abs(sum(probs) - 1) > 1e-6:
        return None
    with_total = target.line is not None and target.over is not None
    if with_total and not _EPS < float(target.over or 0) < 1 - _EPS:
        return None
    line = target.line if with_total else None
    goal = [target.home, target.away] + ([float(target.over or 0)] if with_total else [])
    goal_logit = np.array([_logit(p) for p in goal])
    total_start = float(np.log(start[0] + start[1]))

    def rates(x: np.ndarray) -> tuple[float, float]:
        lam_h = float(np.clip(np.exp(x[0]), *_LAMBDA_BOUNDS))
        lam_a = float(np.clip(np.exp(x[1]), *_LAMBDA_BOUNDS))
        return lam_h, lam_a

    def loss(x: np.ndarray) -> float:
        lam_h, lam_a = rates(x)
        got = np.array([_logit(p) for p in _outcomes(lam_h, lam_a, rho, line)])
        value = float(((got - goal_logit) ** 2).sum())
        if not with_total:
            # Total de buts du moteur conservé (pénalité faible : le 1-N-2 passe d'abord).
            value += 0.05 * (float(np.log(lam_h + lam_a)) - total_start) ** 2
        return value

    def error_of(x: np.ndarray) -> float:
        got = _outcomes(*rates(x), rho, line)
        return max(abs(g - t) for g, t in zip(got, goal, strict=True))

    best: tuple[float, np.ndarray] | None = None
    # Le point de départ du moteur suffit presque toujours ; les autres ne servent que si
    # la recherche s'est arrêtée loin de la cible.
    for guess in (start, (1.5, 1.2), (2.2, 0.7), (0.7, 2.2)):
        res = minimize(
            loss,
            np.log(np.clip(guess, *_LAMBDA_BOUNDS)),
            method="Nelder-Mead",
            options={"xatol": 1e-4, "fatol": 1e-8, "maxiter": 200},
        )
        if best is None or res.fun < best[0]:
            best = (float(res.fun), res.x)
        if error_of(best[1]) <= MAX_FIT_ERROR:
            break
    assert best is not None
    error = error_of(best[1])
    if error > MAX_FIT_ERROR:
        return None
    lam_h, lam_a = rates(best[1])
    return Fit(lam_home=lam_h, lam_away=lam_a, error=error)


def reference_target(quotes: Mapping[str, float]) -> MarketTarget | None:
    """Cible de calage tirée des cotes du bookmaker de référence.

    ``quotes`` : clé du moteur (« 1X2||home », « OU|2.5|over ») → cote. Il faut le 1-N-2
    complet. Plus/moins : la ligne demi-entière dont les deux côtés sont cotés et la plus
    équilibrée (cotes les plus proches l'une de l'autre) ; à égalité, 2,5.
    """
    main = power_devig([quotes.get(f"1X2||{s}", float("nan")) for s in ("home", "draw", "away")])
    if main is None:
        return None
    best: tuple[float, float, float] | None = None  # (déséquilibre, ligne, proba du plus)
    for key, price in quotes.items():
        market, line, side = key.split("|")
        if market != "OU" or side != "over":
            continue
        try:
            value = float(line)
        except ValueError:
            continue
        if value % 1 != 0.5:  # lignes entières et au quart : remboursements possibles
            continue
        pair = power_devig([price, quotes.get(f"OU|{line}|under", float("nan"))])
        if pair is None:
            continue
        rank = (abs(pair[0] - 0.5), abs(value - 2.5))
        if best is None or rank < (best[0], abs(best[1] - 2.5)):
            best = (rank[0], value, pair[0])
    home, draw, away = main
    if best is None:
        return MarketTarget(home, draw, away)
    return MarketTarget(home, draw, away, line=best[1], over=best[2])
