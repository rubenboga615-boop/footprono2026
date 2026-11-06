"""Moteur des sélections nationales (étude du 06/11/2026, docs/MOTEUR.md).

- Note Elo par sélection, mise à jour après chaque match : K = 40 en compétition
  officielle, 20 en amical ; avantage du terrain 60 (aucun sur terrain neutre) ; l'écart
  de buts pèse comme pour les coupes. Départ à 1 500.
- Niveaux de buts : moyenne mobile des buts marqués et encaissés (poids 0,08 : une
  douzaine de matchs, une sélection en joue une dizaine par an).
- Buts de chaque équipe : régression de Poisson (écart de note, terrain neutre, niveaux de
  buts), Dixon-Coles et part des buts en 1re période ; apprise au 1er janvier de chaque
  année sur les matchs officiels des deux années d'avant (les niveaux des sélections
  changent vite ; trois ou quatre ans : moins bien).
- Pronostics des matchs officiels seulement ; les amicaux servent aux notes.
- Marchés publiés (``published``) : ceux qui ont passé l'étude dans au moins quatre
  réglages sur cinq. 1X2 et double chance : pas de pronostic quand une équipe est
  annoncée à 90 % ou plus (favoris écrasants surestimés : 95 % annoncés, 90 % gagnés) ;
  le match n'est alors pas pronostiqué du tout (``MAX_FAVOURITE``).
"""

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize_scalar
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.engine.cups import _dixon_coles_nll, poisson_regression, result_probabilities
from footprono.engine.markets import Selection, derive_markets
from footprono.engine.scores import score_distribution
from footprono.ingestion.reference import NATIONS, NATIONS_BY_CODE

ENGINE_VERSION = "sélections 1.0"
K_OFFICIAL, K_FRIENDLY, HOME = 40.0, 20.0, 60.0
START = 1500.0
LEVEL_RATE, LEVEL_START, LEVEL_FLOOR = 0.08, 1.3, 0.2
WINDOW_YEARS = 2
MIN_TRAIN = 300
MAX_FAVOURITE = 0.90
AFRICA = frozenset({"CAN", "CANQ", "WCQ_AFR"})
EPS = 1e-12

FloatArray = NDArray[np.float64]

PUBLISHED_LINES = {
    "OU": {"0.5", "1.5", "2.5"},
    "HT_OU": {"0.5", "1.5"},
    "EH": {"-2", "-3", "1"},
    "OU_BTTS": {"2.5"},
    "TEAM_OU_HOME": {"0.5", "2.5", "3.5"},
    "TEAM_OU_AWAY": {"1.5", "3.5"},
}
PUBLISHED_PLAIN = {"1X2", "DC", "BTTS", "HT_1X2"}


def published(key: str) -> bool:
    """La clé « MARCHÉ|ligne|issue » fait-elle partie des marchés publiés des sélections ?"""
    market, line, _ = key.split("|")
    if market in PUBLISHED_PLAIN:
        return True
    return line in PUBLISHED_LINES.get(market, set())


def official(competition: str) -> bool:
    ref = NATIONS_BY_CODE.get(competition)
    return ref is not None and ref.official


@dataclass(frozen=True)
class NationMatch:
    match_id: int
    day: date
    competition: str
    home: int
    away: int
    neutral: bool
    finished: bool
    hg: int | None
    ag: int | None
    hg_ht: int | None = None
    ag_ht: int | None = None


_MATCHES = text(
    """
    SELECT m.id, m.match_date, c.code, m.home_team_id, m.away_team_id, m.neutral,
           m.status = 'finished', m.home_goals, m.away_goals, m.home_goals_ht, m.away_goals_ht
    FROM matches m
    JOIN seasons s ON s.id = m.season_id
    JOIN competitions c ON c.id = s.competition_id
    WHERE c.code = ANY(CAST(:codes AS text[])) AND m.status <> 'cancelled'
    ORDER BY m.match_date, m.kickoff_at NULLS LAST, m.id
    """
)


async def load_matches(session: AsyncSession) -> list[NationMatch]:
    rows = (await session.execute(_MATCHES, {"codes": [n.code for n in NATIONS]})).all()
    return [NationMatch(*r) for r in rows]


def _goal_weight(hg: int, ag: int) -> float:
    d = abs(hg - ag)
    return 1.0 if d <= 1 else 1.5 if d == 2 else (11 + d) / 8


@dataclass(frozen=True)
class Features:
    diff: float
    neutral: bool
    attack_home: float
    defence_home: float
    attack_away: float
    defence_away: float


@dataclass(frozen=True)
class Sample:
    day: date
    competition: str
    features: Features
    hg: int
    ag: int
    hg_ht: int | None
    ag_ht: int | None

    @property
    def outcome(self) -> int:
        return 0 if self.hg > self.ag else 1 if self.hg == self.ag else 2


@dataclass
class State:
    """Notes et niveaux de buts ; ``samples`` : matchs officiels joués."""

    values: dict[int, float] = field(default_factory=lambda: defaultdict(lambda: START))
    attack: dict[int, float] = field(default_factory=lambda: defaultdict(lambda: LEVEL_START))
    defence: dict[int, float] = field(default_factory=lambda: defaultdict(lambda: LEVEL_START))
    samples: list[Sample] = field(default_factory=list)

    def rating(self, team: int) -> float:
        return self.values[team]

    def features(self, m: NationMatch) -> Features:
        return Features(
            diff=self.values[m.home] + (0.0 if m.neutral else HOME) - self.values[m.away],
            neutral=m.neutral,
            attack_home=self.attack[m.home], defence_home=self.defence[m.home],
            attack_away=self.attack[m.away], defence_away=self.defence[m.away],
        )  # fmt: skip

    def update(self, m: NationMatch) -> None:
        assert m.hg is not None
        assert m.ag is not None
        f = self.features(m)
        if official(m.competition):
            self.samples.append(Sample(m.day, m.competition, f, m.hg, m.ag, m.hg_ht, m.ag_ht))
        expected = 1 / (1 + 10 ** (-f.diff / 400))
        result = 1.0 if m.hg > m.ag else 0.5 if m.hg == m.ag else 0.0
        k = (K_OFFICIAL if official(m.competition) else K_FRIENDLY) * _goal_weight(m.hg, m.ag)
        self.values[m.home] += k * (result - expected)
        self.values[m.away] -= k * (result - expected)
        for team, scored, conceded in ((m.home, m.hg, m.ag), (m.away, m.ag, m.hg)):
            self.attack[team] += LEVEL_RATE * (scored - self.attack[team])
            self.defence[team] += LEVEL_RATE * (conceded - self.defence[team])


def build_state(matches: Sequence[NationMatch], until: date) -> State:
    """État après tous les matchs joués avant ``until``."""
    state = State()
    for m in matches:
        if m.day >= until:
            break
        if m.finished and m.hg is not None and m.ag is not None:
            state.update(m)
    return state


def _log_level(x: float) -> float:
    return math.log(max(x, LEVEL_FLOOR) / LEVEL_START)


def design(features: Sequence[Features], home: bool) -> FloatArray:
    s = 1.0 if home else -1.0
    rows = []
    for f in features:
        attack, defence = (
            (f.attack_home, f.defence_away) if home else (f.attack_away, f.defence_home)
        )
        rows.append([
            1.0, s * f.diff / 400, 1.0 if f.neutral else 0.0,
            _log_level(attack), _log_level(defence),
        ])  # fmt: skip
    return np.array(rows, dtype=np.float64)


@dataclass(frozen=True)
class GoalModel:
    year: int
    home: tuple[float, ...]
    away: tuple[float, ...]
    rho: float
    share_home: float
    share_away: float
    matches: int

    def rates(self, features: Sequence[Features]) -> tuple[FloatArray, FloatArray]:
        lh = np.exp(np.clip(design(features, True) @ np.array(self.home), -5, 3))
        la = np.exp(np.clip(design(features, False) @ np.array(self.away), -5, 3))
        return lh, la


def training(samples: Sequence[Sample], year: int) -> list[Sample]:
    return [s for s in samples if date(year - WINDOW_YEARS, 1, 1) <= s.day < date(year, 1, 1)]


def fit_model(samples: Sequence[Sample], year: int) -> GoalModel:
    """Modèle de l'année ``year`` : matchs officiels des deux années d'avant."""
    train = training(samples, year)
    if len(train) < MIN_TRAIN:
        raise ValueError(f"trop peu de matchs de sélections pour apprendre ({len(train)})")
    feats = [s.features for s in train]
    hg = np.array([s.hg for s in train], dtype=np.float64)
    ag = np.array([s.ag for s in train], dtype=np.float64)
    beta_h = poisson_regression(design(feats, True), hg)
    beta_a = poisson_regression(design(feats, False), ag)
    lh = np.exp(np.clip(design(feats, True) @ beta_h, -5, 3))
    la = np.exp(np.clip(design(feats, False) @ beta_a, -5, 3))
    rho = float(
        minimize_scalar(
            _dixon_coles_nll, bounds=(-0.2, 0.2), method="bounded", args=(lh, la, hg, ag)
        ).x
    )
    with_ht = [s for s in train if s.hg_ht is not None and s.ag_ht is not None]
    share_h = sum(s.hg_ht or 0 for s in with_ht) / max(sum(s.hg for s in with_ht), 1)
    share_a = sum(s.ag_ht or 0 for s in with_ht) / max(sum(s.ag for s in with_ht), 1)
    return GoalModel(
        year, tuple(map(float, beta_h)), tuple(map(float, beta_a)), rho, share_h, share_a,
        len(train),
    )  # fmt: skip


@dataclass(frozen=True)
class Prediction:
    lambda_home: float
    lambda_away: float
    markets: dict[str, Selection]


def predict(
    model: GoalModel, features: Sequence[Features], every_market: bool = False
) -> list[Prediction | None]:
    """Marchés publiés de chaque match (tous avec ``every_market``, pour le backtest) ;
    None : favori écrasant (une équipe à 90 % ou plus), pas de pronostic."""
    if not features:
        return []
    lh, la = model.rates(features)
    results = result_probabilities(lh, la, model.rho)
    out: list[Prediction | None] = []
    for a, b, p in zip(lh, la, results, strict=True):
        if max(p[0], p[2]) >= MAX_FAVOURITE and not every_market:
            out.append(None)
            continue
        dist = score_distribution(float(a), float(b), model.rho, model.share_home, model.share_away)
        markets = {k: s for k, s in derive_markets(dist).items() if every_market or published(k)}
        out.append(Prediction(float(a), float(b), markets))
    return out


_BACKTEST_KEYS = {
    "1X2": ("1X2||home", "1X2||draw", "1X2||away"),
    "OU|2.5": ("OU|2.5|over", "OU|2.5|under"),
    "BTTS": ("BTTS||yes", "BTTS||no"),
}


def _outcome_index(market: str, hg: int, ag: int) -> int:
    if market == "1X2":
        return 0 if hg > ag else 1 if hg == ag else 2
    if market == "OU|2.5":
        return 0 if hg + ag > 2 else 1
    return 0 if hg > 0 and ag > 0 else 1


@dataclass(frozen=True)
class BacktestResult:
    matches: int
    skipped_favourites: int
    log_loss: dict[str, dict[str, float]]
    hit_rate: float
    by_competition: dict[str, dict[str, float]]
    calibration: list[dict[str, Any]]
    years: list[dict[str, Any]]


def backtest(matches: Sequence[NationMatch], first_year: int, last_year: int) -> BacktestResult:
    """Chaque année prédite par le modèle de son 1er janvier (matchs officiels)."""
    samples = build_state(matches, date.max).samples
    probs: dict[str, list[list[float]]] = {k: [] for k in _BACKTEST_KEYS}
    naive: dict[str, list[float]] = {k: [] for k in _BACKTEST_KEYS}
    outcomes: dict[str, list[int]] = {k: [] for k in _BACKTEST_KEYS}
    comps: list[str] = []
    years, skipped = [], 0
    for year in range(first_year, last_year + 1):
        test = [s for s in samples if s.day.year == year]
        if not test:
            continue
        model = fit_model(samples, year)
        train = training(samples, year)
        freq = {
            k: np.bincount([_outcome_index(k, s.hg, s.ag) for s in train], minlength=len(keys))
            / len(train)
            for k, keys in _BACKTEST_KEYS.items()
        }
        n_before = len(comps)
        for sample, pred in zip(test, predict(model, [s.features for s in test]), strict=True):
            if pred is None:
                skipped += 1
                continue
            full = predict(model, [sample.features], every_market=True)[0]
            assert full is not None
            for k, keys in _BACKTEST_KEYS.items():
                index = _outcome_index(k, sample.hg, sample.ag)
                probs[k].append([full.markets[key].win for key in keys])
                naive[k].append(float(freq[k][index]))
                outcomes[k].append(index)
            comps.append(sample.competition)
        p1 = np.array(probs["1X2"][n_before:])
        y1 = np.array(outcomes["1X2"][n_before:])
        if len(y1):
            years.append({
                "year": year, "matches": len(y1),
                "log_loss_1x2": round(float(-np.log(p1[np.arange(len(y1)), y1] + EPS).mean()), 4),
            })  # fmt: skip
    if not comps:
        raise ValueError("aucun match de sélections à évaluer")
    log_loss: dict[str, dict[str, float]] = {}
    for k in _BACKTEST_KEYS:
        p = np.array(probs[k])
        y = np.array(outcomes[k])
        ll = -np.log(p[np.arange(len(y)), y] + EPS)
        log_loss[k] = {
            "model": round(float(ll.mean()), 4),
            "naive": round(float(-np.log(np.array(naive[k]) + EPS).mean()), 4),
        }
    p = np.array(probs["1X2"])
    y = np.array(outcomes["1X2"])
    ll1 = -np.log(p[np.arange(len(y)), y] + EPS)
    nv1 = -np.log(np.array(naive["1X2"]) + EPS)
    groups = {
        "AFRIQUE": [c in AFRICA for c in comps],
        **{c: [x == c for x in comps] for c in {*comps}},
    }
    by_comp = {
        name: {
            "matches": int(np.sum(mask)),
            "log_loss": round(float(ll1[np.array(mask)].mean()), 4),
            "naive_log_loss": round(float(nv1[np.array(mask)].mean()), 4),
        }
        for name, mask in groups.items()
        if np.sum(mask)
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
        skipped_favourites=skipped,
        log_loss=log_loss,
        hit_rate=round(float((p.argmax(axis=1) == y).mean()), 4),
        by_competition=by_comp,
        calibration=calib,
        years=years,
    )
