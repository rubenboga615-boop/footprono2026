"""Chances pendant le match (plan du 10/11/2026, étape 6).

Point de départ : la prévision d'avant-match du moteur (λ domicile, λ extérieur, part des
buts en 1re période). Pendant le match, le score déjà marqué est acquis ; le reste du match
est déroulé minute par minute (``evolve``) : chaque équipe marque au rythme de ses buts
attendus de la période (``s·λ`` puis ``(1-s)·λ``, répartis sur la durée de la période, temps
additionnel moyen ``ADDED`` compris), multiplié par l'effet du score du moment
(``SCORE_EFFECT`` : l'équipe menée pousse, celle qui mène gère).

Le temps est compté uniformément dans chaque période : à vérifier minute par minute sur les
événements gardés (``live_study``) ; seul le repère de la mi-temps l'est sur l'archive (les
scores à la pause y sont, pas les minutes des buts).

Pas de chance calculée après un carton rouge (effet non mesuré) ni en prolongation : le
moteur se tait plutôt que d'afficher un chiffre non vérifié.

Même forme de loi que l'avant-match (``ScoreDistribution``) : tous les marchés sortent de
``derive_markets``, ceux déjà joués valent 0 ou 1.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from footprono.engine.markets import Selection, derive_markets
from footprono.engine.scores import MAX_GOALS, MAX_HT_GOALS, ScoreDistribution

FloatArray = NDArray[np.float64]

HALF = 45
# Temps additionnel moyen de chaque période (minutes) ; à remplacer par la mesure des relevés.
ADDED = (2.0, 5.0)

FIRST_HALF = frozenset({"1H"})
HALF_TIME = frozenset({"HT"})
SECOND_HALF = frozenset({"2H"})
LIVE_STATUSES = FIRST_HALF | HALF_TIME | SECOND_HALF


@dataclass(frozen=True)
class LiveState:
    """Où en est le match : statut API-Football (1H, HT, 2H), minute, temps additionnel,
    score, score de la pause (s'il est connu), cartons rouges."""

    status: str
    minute: int
    extra: int
    home: int
    away: int
    ht_home: int | None = None
    ht_away: int | None = None
    red_home: int = 0
    red_away: int = 0


def remaining(state: LiveState) -> tuple[float, float]:
    """Part du temps qui reste dans la 1re et dans la 2e période (entre 0 et 1)."""
    if state.status in FIRST_HALF:
        length = HALF + ADDED[0]
        played = min(max(state.minute, 0) + max(state.extra, 0), length)
        return 1 - played / length, 1.0
    if state.status in HALF_TIME:
        return 0.0, 1.0
    length = HALF + ADDED[1]
    played = min(max(state.minute - HALF, 0) + max(state.extra, 0), length)
    return 0.0, 1 - played / length


# Effet du score sur le rythme des buts d'une équipe, selon l'écart vu de son côté : mené de
# 2 buts ou plus, mené de 1, à égalité, devant de 1, devant de 2 ou plus. Appris sur les
# saisons 2019-2022 de l'archive (scores à la pause et finaux), vérifié sur 2023-2025
# (docs/MOTEUR.md, « Chances en direct »).
SCORE_EFFECT: tuple[float, float, float, float, float] = (0.9651, 1.1125, 0.9757, 0.9512, 1.0095)

GRID = MAX_GOALS + 1
BUCKET = 5  # minutes par tranche du rythme des buts
BUCKETS = HALF // BUCKET  # 9 tranches de 5 minutes, puis le temps additionnel


@dataclass(frozen=True)
class LiveModel:
    """Rythme des buts au fil du match et effet du score.

    ``first`` et ``second`` : multiplicateur du rythme de base (buts attendus de la période
    répartis sur 45 minutes et le temps additionnel moyen) pour chaque tranche de 5 minutes,
    puis pour le temps additionnel (10 valeurs par période). 1 partout : rythme régulier.
    Appris sur les minutes des buts gardées (``live_study.fit_live_model``)."""

    first: tuple[float, ...] = (1.0,) * (BUCKETS + 1)
    second: tuple[float, ...] = (1.0,) * (BUCKETS + 1)
    effect: tuple[float, ...] = SCORE_EFFECT

    def as_dict(self) -> dict[str, list[float]]:
        return {"first": list(self.first), "second": list(self.second), "effect": list(self.effect)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LiveModel":
        return cls(
            tuple(float(x) for x in d["first"]),
            tuple(float(x) for x in d["second"]),
            tuple(float(x) for x in d["effect"]),
        )

    def profile(self, half: int, played: int, extra: int) -> FloatArray:
        """Multiplicateurs des minutes qui restent dans la période ``half`` (0 ou 1) quand
        ``played`` minutes sont jouées (``extra`` : minutes de temps additionnel jouées)."""
        weights = self.first if half == 0 else self.second
        added = int(np.ceil(ADDED[half]))
        if extra > 0:
            regular: list[float] = []
            rest = max(added - extra, 0)
        else:
            regular = [
                weights[min((k - 1) // BUCKET, BUCKETS - 1)] for k in range(played + 1, HALF + 1)
            ]
            rest = added
        return np.array(regular + [weights[BUCKETS]] * rest, dtype=np.float64)


DEFAULT_MODEL = LiveModel()


def evolve(
    start: FloatArray,
    rate_h: FloatArray | float,
    rate_a: FloatArray | float,
    minutes: float,
    effect: Sequence[float] = SCORE_EFFECT,
    profile: FloatArray | None = None,
) -> FloatArray:
    """Loi du score après ``minutes`` minutes, minute par minute : ``start[..., h, a]`` est la
    loi de départ, ``rate`` les buts attendus par minute de chaque équipe (à égalité de
    situation), multipliés à chaque minute par l'effet du score du moment et, si donné, par
    ``profile`` (une valeur par minute : le rythme du moment du match)."""
    if profile is not None:
        steps, dt = len(profile), 1.0
    else:
        steps = int(np.ceil(minutes - 1e-9))
        dt = minutes / steps if steps > 0 else 0.0
    if steps <= 0:
        return start
    h, a = np.indices((GRID, GRID))
    eff = np.asarray(effect, dtype=np.float64)
    mult_h = eff[np.clip(h - a, -2, 2) + 2]
    mult_a = eff[np.clip(a - h, -2, 2) + 2]
    rh = np.asarray(rate_h, dtype=np.float64)[..., None, None]
    ra = np.asarray(rate_a, dtype=np.float64)[..., None, None]
    p = start
    for t in range(steps):
        m = 1.0 if profile is None else float(profile[t])
        ph = 1 - np.exp(-rh * mult_h * dt * m)
        pa = 1 - np.exp(-ra * mult_a * dt * m)
        new = p * ((1 - ph) * (1 - pa))
        new[..., 1:, :] += (p * ph * (1 - pa))[..., :-1, :]
        new[..., :, 1:] += (p * (1 - ph) * pa)[..., :, :-1]
        new[..., 1:, 1:] += (p * ph * pa)[..., :-1, :-1]
        p = new
    return np.asarray(p, dtype=np.float64)


def _point(h: int, a: int) -> FloatArray:
    out = np.zeros((GRID, GRID))
    out[h, a] = 1.0
    return out


def live_distribution(
    lam_h: float,
    lam_a: float,
    share_h: float,
    share_a: float,
    state: LiveState,
    model: LiveModel = DEFAULT_MODEL,
) -> ScoreDistribution | None:
    """Loi (score de la pause, score final) sachant l'état du match ; None si le moteur ne
    sait pas la calculer (statut hors 1H/HT/2H, carton rouge, score hors des limites)."""
    if state.status not in LIVE_STATUSES or state.red_home or state.red_away:
        return None
    limit = MAX_HT_GOALS if state.status in FIRST_HALF | HALF_TIME else MAX_GOALS
    if max(state.home, state.away) > limit:
        return None
    len1, len2 = HALF + ADDED[0], HALF + ADDED[1]
    first = (share_h * lam_h / len1, share_a * lam_a / len1)
    second = ((1 - share_h) * lam_h / len2, (1 - share_a) * lam_a / len2)
    whole_second = model.profile(1, 0, 0)
    ht_n = MAX_HT_GOALS + 1
    joint = np.zeros((ht_n, ht_n, GRID, GRID))

    if state.status in FIRST_HALF:
        rest = model.profile(0, min(max(state.minute, 0), HALF), max(state.extra, 0))
        ht = evolve(_point(state.home, state.away), *first, 0, model.effect, rest)[:ht_n, :ht_n]
        starts = np.zeros((ht_n, ht_n, GRID, GRID))
        for i in range(ht_n):
            for j in range(ht_n):
                starts[i, j, i, j] = 1.0
        joint = ht[:, :, None, None] * evolve(starts, *second, 0, model.effect, whole_second)
    else:
        if state.status in HALF_TIME or state.ht_home is None or state.ht_away is None:
            hh, ha = state.home, state.away
        else:
            hh, ha = state.ht_home, state.ht_away
        if max(hh, ha) > MAX_HT_GOALS:
            return None
        rest = (
            whole_second
            if state.status in HALF_TIME
            else model.profile(1, min(max(state.minute - HALF, 0), HALF), max(state.extra, 0))
        )
        joint[hh, ha] = evolve(_point(state.home, state.away), *second, 0, model.effect, rest)
    total = joint.sum()
    if total <= 0:
        return None
    return ScoreDistribution(joint=np.asarray(joint / total, dtype=np.float64))


def live_markets(
    lam_h: float,
    lam_a: float,
    share_h: float,
    share_a: float,
    state: LiveState,
    model: LiveModel = DEFAULT_MODEL,
) -> dict[str, Selection] | None:
    dist = live_distribution(lam_h, lam_a, share_h, share_a, state, model)
    return None if dist is None else derive_markets(dist)
