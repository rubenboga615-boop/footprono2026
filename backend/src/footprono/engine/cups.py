"""Moteur des coupes d'Europe : Elo commun aux championnats et aux coupes.

Étude du 07/10/2026 (docs/MOTEUR.md, « Coupes d'Europe ») : 3 989 matchs de coupe de
2022-23 à 2026-27, chacun prédit avec les seuls matchs d'avant lui ; 1X2 log loss
0,961 contre 1,044 pour la référence naïve, calibration à 2 points près entre 10 et
70 %. Résultats seulement (pas de statistiques de coupe) : 1X2 et double chance.

- Une note par équipe, mise à jour après chaque match de nos championnats (K = 10,
  avantage du terrain 65) et de coupe (K = 55, avantage 100, aucun en finale) ; l'écart
  de buts pèse comme dans l'Elo des sélections.
- Une équipe d'un de nos championnats commence à 1 500, une équipe d'ailleurs à 1 350 :
  ses matchs de coupe la situent ensuite.
- Note → probabilités : logit ordonné (domicile, nul, extérieur) appris sur les matchs
  de coupe déjà joués, depuis juillet 2019 (une saison pour que les notes se placent).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
from scipy.optimize import minimize
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.ingestion.reference import CUPS_BY_CODE, LEAGUE_CODES

ENGINE_VERSION = "coupes 1.0"
K_LEAGUE, K_CUP = 10.0, 55.0
HOME_LEAGUE, HOME_CUP = 65.0, 100.0
START_LEAGUE, START_FOREIGN = 1500.0, 1350.0
MAPPING_FROM = date(2019, 7, 1)
EPS = 1e-12


@dataclass(frozen=True)
class CupMatch:
    match_id: int
    day: date
    competition: str
    home: int
    away: int
    neutral: bool
    finished: bool
    hg: int | None
    ag: int | None

    @property
    def cup(self) -> bool:
        return self.competition in CUPS_BY_CODE

    @property
    def outcome(self) -> int:
        assert self.hg is not None
        assert self.ag is not None
        return 0 if self.hg > self.ag else 1 if self.hg == self.ag else 2


_MATCHES = text(
    """
    SELECT m.id, m.match_date, c.code, m.home_team_id, m.away_team_id, m.neutral,
           m.status = 'finished', m.home_goals, m.away_goals
    FROM matches m
    JOIN seasons s ON s.id = m.season_id
    JOIN competitions c ON c.id = s.competition_id
    WHERE c.code = ANY(CAST(:codes AS text[])) AND m.status <> 'cancelled'
    ORDER BY m.match_date, m.kickoff_at NULLS LAST, m.id
    """
)


async def load_matches(session: AsyncSession) -> list[CupMatch]:
    codes = [*LEAGUE_CODES, *CUPS_BY_CODE]
    rows = (await session.execute(_MATCHES, {"codes": codes})).all()
    return [CupMatch(*r) for r in rows]


def _goal_weight(hg: int, ag: int) -> float:
    d = abs(hg - ag)
    return 1.0 if d <= 1 else 1.5 if d == 2 else (11 + d) / 8


@dataclass
class Ratings:
    """Notes au fil des matchs ; ``samples`` : écart avant chaque match de coupe joué."""

    league_teams: set[int]
    values: dict[int, float]
    samples: list[tuple[date, float, int, str]]

    def rating(self, team: int) -> float:
        if team not in self.values:
            self.values[team] = START_LEAGUE if team in self.league_teams else START_FOREIGN
        return self.values[team]

    def diff(self, m: CupMatch) -> float:
        home = 0.0 if m.neutral else (HOME_CUP if m.cup else HOME_LEAGUE)
        return self.rating(m.home) + home - self.rating(m.away)


def build_ratings(matches: Sequence[CupMatch], until: date) -> Ratings:
    """Notes après tous les matchs joués avant ``until``."""
    r = Ratings({t for m in matches if not m.cup for t in (m.home, m.away)}, {}, [])
    for m in matches:
        if m.day >= until:
            break
        if not m.finished or m.hg is None or m.ag is None:
            continue
        d = r.diff(m)
        if m.cup:
            r.samples.append((m.day, d, m.outcome, m.competition))
        expected = 1 / (1 + 10 ** (-d / 400))
        result = 1.0 if m.hg > m.ag else 0.5 if m.hg == m.ag else 0.0
        k = (K_CUP if m.cup else K_LEAGUE) * _goal_weight(m.hg, m.ag)
        r.values[m.home] += k * (result - expected)
        r.values[m.away] -= k * (result - expected)
    return r


def probabilities(theta: Sequence[float] | np.ndarray, diff: np.ndarray) -> np.ndarray:
    """Logit ordonné : (domicile, nul, extérieur) pour chaque écart de note."""
    a1, a2, b = theta
    home = 1 / (1 + np.exp(-(a1 + b * diff)))
    home_or_draw = 1 / (1 + np.exp(-(a2 + b * diff)))
    p = np.stack([home, np.clip(home_or_draw - home, 1e-6, 1), 1 - home_or_draw], axis=1)
    return p / p.sum(axis=1, keepdims=True)


def fit_mapping(samples: Iterable[tuple[date, float, int, str]]) -> tuple[float, float, float]:
    data = [(d, y) for day, d, y, _ in samples if day >= MAPPING_FROM]
    if len(data) < 200:
        raise ValueError(f"trop peu de matchs de coupe pour apprendre ({len(data)})")
    diff = np.array([d for d, _ in data])
    y = np.array([o for _, o in data])

    def loss(t: np.ndarray) -> float:
        p = probabilities(t, diff)
        return float(-np.mean(np.log(p[np.arange(len(y)), y] + EPS)))

    res = minimize(loss, np.array([0.0, 1.0, 0.005]), method="Nelder-Mead",
                   options={"maxiter": 4000, "xatol": 1e-7, "fatol": 1e-10})  # fmt: skip
    a1, a2, b = (float(x) for x in res.x)
    return a1, a2, b


def markets(p_home: float, p_draw: float, p_away: float) -> dict[str, list[float]]:
    """Marchés proposés pour un match de coupe (même format que les championnats)."""

    def q(prob: float) -> list[float]:
        return [round(prob, 6), round(1 / max(prob, EPS), 4)]

    return {
        "1X2||home": q(p_home), "1X2||draw": q(p_draw), "1X2||away": q(p_away),
        "DC||1X": q(p_home + p_draw), "DC||X2": q(p_draw + p_away), "DC||12": q(p_home + p_away),
    }  # fmt: skip


@dataclass(frozen=True)
class BacktestResult:
    matches: int
    log_loss: float
    naive_log_loss: float
    hit_rate: float
    announced: float
    by_competition: dict[str, dict[str, float]]
    calibration: list[dict[str, Any]]


def backtest(matches: Sequence[CupMatch], start: date) -> BacktestResult:
    """Chaque match de coupe depuis ``start`` prédit avec les seuls matchs d'avant lui ;
    correspondance réapprise au début de chaque saison (juillet)."""
    ratings = build_ratings(matches, date.max)
    samples = ratings.samples
    out_p: list[np.ndarray] = []
    out_y: list[int] = []
    comps: list[str] = []
    for season in sorted({s[0].year if s[0].month >= 7 else s[0].year - 1 for s in samples}):
        first = date(season, 7, 1)
        if first < start:
            continue
        past = [s for s in samples if s[0] < first]
        current = [s for s in samples if first <= s[0] < date(season + 1, 7, 1)]
        if not current:
            continue
        theta = fit_mapping(past)
        p = probabilities(theta, np.array([s[1] for s in current]))
        out_p.append(p)
        out_y.extend(s[2] for s in current)
        comps.extend(s[3] for s in current)
    if not out_p:
        raise ValueError("aucun match de coupe à évaluer")
    p = np.vstack(out_p)
    y = np.array(out_y)
    train = np.array([s[2] for s in samples if MAPPING_FROM <= s[0] < start])
    freq = np.bincount(train, minlength=3) / max(len(train), 1)
    ll = -np.log(p[np.arange(len(y)), y] + EPS)
    naive = -np.log(freq[y] + EPS)
    by_comp = {}
    for code in CUPS_BY_CODE:
        mask = np.array([c == code for c in comps])
        if mask.any():
            by_comp[code] = {
                "matches": int(mask.sum()),
                "log_loss": round(float(ll[mask].mean()), 4),
                "naive_log_loss": round(float(naive[mask].mean()), 4),
            }
    calib: list[dict[str, Any]] = []
    flat_p = p.ravel()
    flat_o = (np.arange(3)[None, :] == y[:, None]).ravel()
    for i in range(10):
        m = (flat_p >= i / 10) & (flat_p < (i + 1) / 10)
        if m.any():
            calib.append({
                "range": f"{i / 10:.1f}-{(i + 1) / 10:.1f}".replace(".", ","),
                "count": int(m.sum()),
                "announced": round(float(flat_p[m].mean()), 4),
                "observed": round(float(flat_o[m].mean()), 4),
            })  # fmt: skip
    return BacktestResult(
        matches=len(y),
        log_loss=round(float(ll.mean()), 4),
        naive_log_loss=round(float(naive.mean()), 4),
        hit_rate=round(float((p.argmax(axis=1) == y).mean()), 4),
        announced=round(float(p.max(axis=1).mean()), 4),
        by_competition=by_comp,
        calibration=calib,
    )
