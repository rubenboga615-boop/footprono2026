"""Distribution des scores d'un match : fin de match et mi-temps, cohérentes.

- Fin de match : Dixon-Coles (Poisson corrigée pour 0-0, 1-0, 0-1, 1-1).
- Mi-temps : chaque période est une Poisson (part ``s`` des buts en 1re
  période). La loi jointe (score à la mi-temps, score final) est ensuite
  recalée pour que sa marge « score final » soit **exactement** la loi
  Dixon-Coles : tous les marchés, fin de match comme mi-temps, sortent de la
  même distribution (principe n° 5).
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.stats import poisson

MAX_GOALS = 10  # buts par équipe sur le match (masse au-delà : négligeable)
MAX_HT_GOALS = 6  # buts par équipe à la mi-temps

FloatArray = NDArray[np.float64]


def dixon_coles_matrix(lam_h: float, lam_a: float, rho: float) -> FloatArray:
    goals = np.arange(MAX_GOALS + 1)
    m = np.outer(poisson.pmf(goals, lam_h), poisson.pmf(goals, lam_a))
    m[0, 0] *= 1 - lam_h * lam_a * rho
    m[0, 1] *= 1 + lam_h * rho
    m[1, 0] *= 1 + lam_a * rho
    m[1, 1] *= 1 - rho
    m = np.clip(m, 0, None)
    return np.asarray(m / m.sum(), dtype=np.float64)


@dataclass(frozen=True)
class ScoreDistribution:
    """``joint[i, j, k, l]`` = P(mi-temps i-j et score final k-l)."""

    joint: FloatArray

    @property
    def full_time(self) -> FloatArray:
        return np.asarray(self.joint.sum(axis=(0, 1)), dtype=np.float64)

    @property
    def half_time(self) -> FloatArray:
        return np.asarray(self.joint.sum(axis=(2, 3)), dtype=np.float64)


def score_distribution(
    lam_h: float, lam_a: float, rho: float, share_h: float, share_a: float
) -> ScoreDistribution:
    ft = dixon_coles_matrix(lam_h, lam_a, rho)
    ht_goals = np.arange(MAX_HT_GOALS + 1)
    ft_goals = np.arange(MAX_GOALS + 1)
    p1h = poisson.pmf(ht_goals, share_h * lam_h)
    p1a = poisson.pmf(ht_goals, share_a * lam_a)
    p2h = poisson.pmf(ft_goals, (1 - share_h) * lam_h)
    p2a = poisson.pmf(ft_goals, (1 - share_a) * lam_a)

    # Buts de 2e période = score final - score à la mi-temps (0 si impossible).
    diff = ft_goals[None, :] - ht_goals[:, None]  # [i, k]
    second_h = np.where(diff >= 0, p2h[np.clip(diff, 0, MAX_GOALS)], 0.0)
    second_a = np.where(diff >= 0, p2a[np.clip(diff, 0, MAX_GOALS)], 0.0)
    joint = (
        p1h[:, None, None, None]
        * p1a[None, :, None, None]
        * second_h[:, None, :, None]
        * second_a[None, :, None, :]
    )
    independent_ft = joint.sum(axis=(0, 1))
    scale = np.divide(ft, independent_ft, out=np.zeros_like(ft), where=independent_ft > 0)
    joint = joint * scale[None, None, :, :]
    return ScoreDistribution(joint=np.asarray(joint / joint.sum(), dtype=np.float64))
