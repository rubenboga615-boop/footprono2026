"""Moteur des coupes d'Europe : modèle des buts commun aux trois coupes.

Étude du 06/11/2026 (docs/MOTEUR.md, « Coupes d'Europe ») : 4 151 matchs de coupe de
2022-23 à 2026-27, chaque saison prédite avec les seules saisons d'avant ; 97 sélections
évaluées ; seules celles qui battent la référence naïve chaque saison et restent calibrées
sont publiées (``published``) : 1X2, double chance, les deux marquent, plus/moins 0,5 but
et plus/moins 1,5 but à la mi-temps.

- Note Elo par équipe, mise à jour après chaque match de nos championnats (K = 10,
  avantage du terrain 65) et de coupe (K = 55, avantage 100, aucun en finale) ; l'écart
  de buts pèse comme dans l'Elo des sélections. Équipe de nos championnats : 1 500 au
  départ ; d'ailleurs : 1 350.
- Niveaux de buts : moyenne mobile des buts marqués et encaissés par chaque équipe, tous
  matchs confondus (poids 0,04 : une trentaine de matchs).
- Buts de chaque équipe : régression de Poisson (écart de note, terrain neutre, niveaux de
  buts, équipe de nos championnats contre équipe d'ailleurs), puis Dixon-Coles et part des
  buts en 1re période, comme dans les championnats. Apprise au 1er juillet de chaque saison
  sur les matchs de coupe depuis juillet 2019, sans la période COVID (stades vides, phase
  finale de 2020 à Lisbonne).
- 1X2 et double chance : correction de calibration (logistique sur la probabilité du
  domicile) apprise sur les prédictions des saisons passées, faites chacune avec un
  modèle qui ne les connaissait pas : les matchs serrés donnaient trop peu au club qui
  reçoit (35 % annoncés, 40 % gagnés).
"""

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize, minimize_scalar
from scipy.stats import poisson
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.engine.markets import Selection, derive_markets
from footprono.engine.scores import score_distribution
from footprono.ingestion.reference import CUPS_BY_CODE, LEAGUE_CODES

ENGINE_VERSION = "coupes 2.0"
K_LEAGUE, K_CUP = 10.0, 55.0
HOME_LEAGUE, HOME_CUP = 65.0, 100.0
START_LEAGUE, START_FOREIGN = 1500.0, 1350.0
LEVEL_RATE, LEVEL_START, LEVEL_FLOOR = 0.04, 1.35, 0.2
FIT_FROM = date(2019, 7, 1)
COVID = (date(2020, 3, 1), date(2021, 7, 1))
# Première saison dont les prédictions (hors échantillon) servent à la correction du 1X2.
CORRECTION_FROM = 2022
MIN_TRAIN = 300
MAXG = 11
EPS = 1e-12

FloatArray = NDArray[np.float64]

# Marchés publiés : ceux qui ont passé l'étude du 06/11/2026 (toutes leurs issues), par
# tranches de 10 % (3 points d'écart au plus) et par le test de Hosmer-Lemeshow sur
# 2023-2026. Plus/moins 1,5 à 5,5 et handicaps : niveau de buts trop changeant d'une
# saison à l'autre (2,76 buts annoncés, 2,95 observés en 2023-24) ; non publiés.
PUBLISHED_LINES = {"OU": {"0.5"}, "HT_OU": {"1.5"}}
PUBLISHED_PLAIN = {"1X2", "DC", "BTTS"}


def published(key: str) -> bool:
    """La clé « MARCHÉ|ligne|issue » fait-elle partie des marchés publiés des coupes ?"""
    market, line, _ = key.split("|")
    if market in PUBLISHED_PLAIN:
        return True
    return line in PUBLISHED_LINES.get(market, set())


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
    hg_ht: int | None = None
    ag_ht: int | None = None

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
           m.status = 'finished', m.home_goals, m.away_goals, m.home_goals_ht, m.away_goals_ht
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


@dataclass(frozen=True)
class Features:
    """Ce que le modèle sait d'un match de coupe avant son coup d'envoi."""

    diff: float  # note domicile + avantage du terrain - note extérieur
    neutral: bool
    attack_home: float
    defence_home: float
    attack_away: float
    defence_away: float
    pool: float  # +1 : domicile de nos championnats contre une équipe d'ailleurs ; -1 : inverse


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
    """Notes et niveaux de buts au fil des matchs ; ``samples`` : matchs de coupe joués."""

    league_teams: set[int]
    values: dict[int, float] = field(default_factory=dict)
    attack: dict[int, float] = field(default_factory=lambda: defaultdict(lambda: LEVEL_START))
    defence: dict[int, float] = field(default_factory=lambda: defaultdict(lambda: LEVEL_START))
    samples: list[Sample] = field(default_factory=list)

    def rating(self, team: int) -> float:
        if team not in self.values:
            self.values[team] = START_LEAGUE if team in self.league_teams else START_FOREIGN
        return self.values[team]

    def diff(self, m: CupMatch) -> float:
        home = 0.0 if m.neutral else (HOME_CUP if m.cup else HOME_LEAGUE)
        return self.rating(m.home) + home - self.rating(m.away)

    def features(self, m: CupMatch) -> Features:
        return Features(
            diff=self.diff(m), neutral=m.neutral,
            attack_home=self.attack[m.home], defence_home=self.defence[m.home],
            attack_away=self.attack[m.away], defence_away=self.defence[m.away],
            pool=float(m.home in self.league_teams) - float(m.away in self.league_teams),
        )  # fmt: skip

    def update(self, m: CupMatch) -> None:
        assert m.hg is not None
        assert m.ag is not None
        if m.cup:
            self.samples.append(
                Sample(m.day, m.competition, self.features(m), m.hg, m.ag, m.hg_ht, m.ag_ht)
            )
        d = self.diff(m)
        expected = 1 / (1 + 10 ** (-d / 400))
        result = 1.0 if m.hg > m.ag else 0.5 if m.hg == m.ag else 0.0
        k = (K_CUP if m.cup else K_LEAGUE) * _goal_weight(m.hg, m.ag)
        self.values[m.home] += k * (result - expected)
        self.values[m.away] -= k * (result - expected)
        for team, scored, conceded in ((m.home, m.hg, m.ag), (m.away, m.ag, m.hg)):
            self.attack[team] += LEVEL_RATE * (scored - self.attack[team])
            self.defence[team] += LEVEL_RATE * (conceded - self.defence[team])


def build_state(matches: Sequence[CupMatch], until: date) -> State:
    """État après tous les matchs joués avant ``until``."""
    state = State({t for m in matches if not m.cup for t in (m.home, m.away)})
    for m in matches:
        if m.day >= until:
            break
        if m.finished and m.hg is not None and m.ag is not None:
            state.update(m)
    return state


def _log_level(x: float) -> float:
    return math.log(max(x, LEVEL_FLOOR) / LEVEL_START)


def design(features: Sequence[Features], home: bool) -> FloatArray:
    """Variables de la régression des buts du club qui reçoit (``home``) ou de l'autre."""
    s = 1.0 if home else -1.0
    rows = []
    for f in features:
        attack, defence = (
            (f.attack_home, f.defence_away) if home else (f.attack_away, f.defence_home)
        )
        rows.append([
            1.0, s * f.diff / 400, 1.0 if f.neutral else 0.0,
            _log_level(attack), _log_level(defence), s * f.pool,
        ])  # fmt: skip
    return np.array(rows, dtype=np.float64)


def poisson_regression(x: FloatArray, y: FloatArray, ridge: float = 1e-4) -> FloatArray:
    """Régression de Poisson (moindres carrés repondérés), légèrement régularisée."""
    beta = np.zeros(x.shape[1])
    beta[0] = math.log(max(float(y.mean()), 0.1))
    for _ in range(50):
        eta = np.clip(x @ beta, -5, 3)
        mu = np.exp(eta)
        z = eta + (y - mu) / mu
        a = x.T @ (mu[:, None] * x) + ridge * np.eye(x.shape[1])
        new = np.linalg.solve(a, x.T @ (mu * z))
        done = float(np.max(np.abs(new - beta))) < 1e-9
        beta = new
        if done:
            break
    return np.asarray(beta, dtype=np.float64)


def _dixon_coles_nll(rho: float, lh: FloatArray, la: FloatArray, hg: FloatArray,
                     ag: FloatArray) -> float:  # fmt: skip
    tau = np.ones_like(lh)
    tau = np.where((hg == 0) & (ag == 0), 1 - lh * la * rho, tau)
    tau = np.where((hg == 0) & (ag == 1), 1 + lh * rho, tau)
    tau = np.where((hg == 1) & (ag == 0), 1 + la * rho, tau)
    tau = np.where((hg == 1) & (ag == 1), 1 - rho, tau)
    p = poisson.pmf(hg, lh) * poisson.pmf(ag, la) * np.clip(tau, EPS, None)
    return float(-np.sum(np.log(p + EPS)))


def _matrices(lh: FloatArray, la: FloatArray, rho: float) -> FloatArray:
    """Matrices Dixon-Coles des scores (``n, MAXG, MAXG``)."""
    g = np.arange(MAXG)
    m = (
        poisson.pmf(g[None, :], lh[:, None])[:, :, None]
        * poisson.pmf(g[None, :], la[:, None])[:, None, :]
    )
    m[:, 0, 0] *= 1 - lh * la * rho
    m[:, 0, 1] *= 1 + lh * rho
    m[:, 1, 0] *= 1 + la * rho
    m[:, 1, 1] *= 1 - rho
    m = np.clip(m, 0, None)
    return np.asarray(m / m.sum(axis=(1, 2), keepdims=True), dtype=np.float64)


def result_probabilities(lh: FloatArray, la: FloatArray, rho: float) -> FloatArray:
    """(domicile, nul, extérieur) du modèle des buts, avant correction."""
    m = _matrices(lh, la, rho)
    h, a = np.indices((MAXG, MAXG))
    return np.stack(
        [m[:, h > a].sum(axis=1), m[:, h == a].sum(axis=1), m[:, h < a].sum(axis=1)], axis=1
    )


@dataclass(frozen=True)
class GoalModel:
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


def training(samples: Sequence[Sample], cutoff: date) -> list[Sample]:
    return [s for s in samples if FIT_FROM <= s.day < cutoff and not COVID[0] <= s.day < COVID[1]]


def fit_goals(samples: Sequence[Sample], cutoff: date) -> GoalModel:
    """Modèle des buts appris sur les matchs de coupe joués avant ``cutoff``."""
    train = training(samples, cutoff)
    if len(train) < MIN_TRAIN:
        raise ValueError(f"trop peu de matchs de coupe pour apprendre ({len(train)})")
    feats = [s.features for s in train]
    hg = np.array([s.hg for s in train], dtype=np.float64)
    ag = np.array([s.ag for s in train], dtype=np.float64)
    beta_h = poisson_regression(design(feats, True), hg)
    beta_a = poisson_regression(design(feats, False), ag)
    model = GoalModel(tuple(map(float, beta_h)), tuple(map(float, beta_a)), 0.0, 0.45, 0.45, 0)
    lh, la = model.rates(feats)
    rho = float(
        minimize_scalar(
            _dixon_coles_nll, bounds=(-0.2, 0.2), method="bounded", args=(lh, la, hg, ag)
        ).x
    )
    with_ht = [s for s in train if s.hg_ht is not None and s.ag_ht is not None]
    share_h = sum(s.hg_ht or 0 for s in with_ht) / max(sum(s.hg for s in with_ht), 1)
    share_a = sum(s.ag_ht or 0 for s in with_ht) / max(sum(s.ag for s in with_ht), 1)
    return GoalModel(model.home, model.away, rho, share_h, share_a, len(train))


def season_of(day: date) -> int:
    return day.year if day.month >= 7 else day.year - 1


def _logit(p: FloatArray) -> FloatArray:
    q = np.clip(p, 1e-4, 1 - 1e-4)
    return np.asarray(np.log(q / (1 - q)), dtype=np.float64)


@dataclass(frozen=True)
class Correction:
    """Correction du 1X2 : P = logistique(a + b · logit(p)) pour le domicile et l'extérieur.

    Seul le domicile est corrigé (l'étude : corriger l'extérieur dégrade le pronostic) ; le
    nul est ce qui reste."""

    home: tuple[float, float] = (0.0, 1.0)
    away: tuple[float, float] = (0.0, 1.0)
    matches: int = 0

    def apply(self, p: FloatArray) -> FloatArray:
        h = 1 / (1 + np.exp(-(self.home[0] + self.home[1] * _logit(p[:, 0]))))
        a = 1 / (1 + np.exp(-(self.away[0] + self.away[1] * _logit(p[:, 2]))))
        d = np.clip(1 - h - a, 0.03, None)
        out = np.stack([h, d, a], axis=1)
        return np.asarray(out / out.sum(axis=1, keepdims=True), dtype=np.float64)


def _fit_side(p: FloatArray, hit: FloatArray) -> tuple[float, float]:
    z = _logit(p)

    def nll(ab: FloatArray) -> float:
        q = np.clip(1 / (1 + np.exp(-(ab[0] + ab[1] * z))), 1e-9, 1 - 1e-9)
        return float(-np.mean(hit * np.log(q) + (1 - hit) * np.log(1 - q)))

    res = minimize(nll, np.array([0.0, 1.0]), method="Nelder-Mead")
    return float(res.x[0]), float(res.x[1])


def out_of_sample(samples: Sequence[Sample], season: int) -> tuple[FloatArray, list[Sample]]:
    """1X2 brut de la saison ``season`` prédite par le modèle appris avant elle."""
    start = date(season, 7, 1)
    test = [s for s in samples if start <= s.day < date(season + 1, 7, 1)]
    if not test:
        return np.zeros((0, 3)), []
    model = fit_goals(samples, start)
    lh, la = model.rates([s.features for s in test])
    return result_probabilities(lh, la, model.rho), test


def fit_correction(samples: Sequence[Sample], season: int) -> Correction:
    """Correction apprise sur les saisons ``CORRECTION_FROM`` à ``season - 1``."""
    probs, outcomes = [], []
    for s in range(CORRECTION_FROM, season):
        p, test = out_of_sample(samples, s)
        probs.append(p)
        outcomes += [t.outcome for t in test]
    if len(outcomes) < MIN_TRAIN:
        return Correction()
    p = np.vstack(probs)
    y = np.array(outcomes)
    return Correction(home=_fit_side(p[:, 0], (y == 0).astype(float)), matches=len(y))


@dataclass(frozen=True)
class CupModel:
    season: int
    goals: GoalModel
    correction: Correction


def fit_model(samples: Sequence[Sample], as_of: date) -> CupModel:
    """Modèle de la saison de ``as_of`` : appris au 1er juillet, sur les saisons d'avant."""
    season = season_of(as_of)
    return CupModel(season, fit_goals(samples, date(season, 7, 1)), fit_correction(samples, season))


@dataclass(frozen=True)
class Prediction:
    lambda_home: float
    lambda_away: float
    markets: dict[str, Selection]


def predict(
    model: CupModel, features: Sequence[Features], every_market: bool = False
) -> list[Prediction]:
    """Marchés publiés de chaque match (tous avec ``every_market``, pour le backtest) ;
    1X2 et double chance corrigés."""
    if not features:
        return []
    g = model.goals
    lh, la = g.rates(features)
    corrected = model.correction.apply(result_probabilities(lh, la, g.rho))
    out = []
    for a, b, (ph, pd, pa) in zip(lh, la, corrected, strict=True):
        dist = score_distribution(float(a), float(b), g.rho, g.share_home, g.share_away)
        markets = {k: s for k, s in derive_markets(dist).items() if every_market or published(k)}
        ph, pd, pa = float(ph), float(pd), float(pa)
        markets.update({
            "1X2||home": Selection(win=ph), "1X2||draw": Selection(win=pd),
            "1X2||away": Selection(win=pa), "DC||1X": Selection(win=ph + pd),
            "DC||X2": Selection(win=pd + pa), "DC||12": Selection(win=ph + pa),
        })  # fmt: skip
        out.append(Prediction(float(a), float(b), markets))
    return out


# Sélections suivies par le backtest (issue gagnante d'un marché à deux ou trois issues).
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
    log_loss: dict[str, dict[str, float]]
    hit_rate: float
    announced: float
    by_competition: dict[str, dict[str, float]]
    calibration: list[dict[str, Any]]
    seasons: list[dict[str, Any]]


def backtest(matches: Sequence[CupMatch], start: date) -> BacktestResult:
    """Chaque saison depuis ``start`` prédite par le modèle de son 1er juillet."""
    samples = build_state(matches, date.max).samples
    probs: dict[str, list[list[float]]] = {k: [] for k in _BACKTEST_KEYS}
    naive: dict[str, list[float]] = {k: [] for k in _BACKTEST_KEYS}
    outcomes: dict[str, list[int]] = {k: [] for k in _BACKTEST_KEYS}
    comps: list[str] = []
    seasons_out = []
    for season in sorted({season_of(s.day) for s in samples}):
        first = date(season, 7, 1)
        test = [s for s in samples if first <= s.day < date(season + 1, 7, 1)]
        if first < start or not test:
            continue
        model = fit_model(samples, first)
        preds = predict(model, [s.features for s in test], every_market=True)
        train = training(samples, first)
        freq = {
            k: np.bincount([_outcome_index(k, s.hg, s.ag) for s in train], minlength=len(keys))
            / len(train)
            for k, keys in _BACKTEST_KEYS.items()
        }
        for sample, pred in zip(test, preds, strict=True):
            for k, keys in _BACKTEST_KEYS.items():
                index = _outcome_index(k, sample.hg, sample.ag)
                probs[k].append([pred.markets[key].win for key in keys])
                naive[k].append(float(freq[k][index]))
                outcomes[k].append(index)
            comps.append(sample.competition)
        p1 = np.array(probs["1X2"][-len(test) :])
        y1 = np.array(outcomes["1X2"][-len(test) :])
        seasons_out.append({
            "season": season, "matches": len(test),
            "log_loss_1x2": round(float(-np.log(p1[np.arange(len(y1)), y1] + EPS).mean()), 4),
            "correction": {"home": [round(x, 3) for x in model.correction.home],
                           "away": [round(x, 3) for x in model.correction.away]},
        })  # fmt: skip
    if not comps:
        raise ValueError("aucun match de coupe à évaluer")
    log_loss: dict[str, dict[str, float]] = {}
    ll_1x2 = np.zeros(0)
    naive_1x2 = np.zeros(0)
    for k in _BACKTEST_KEYS:
        p = np.array(probs[k])
        y = np.array(outcomes[k])
        ll = -np.log(p[np.arange(len(y)), y] + EPS)
        nv = -np.log(np.array(naive[k]) + EPS)
        log_loss[k] = {"model": round(float(ll.mean()), 4), "naive": round(float(nv.mean()), 4)}
        if k == "1X2":
            ll_1x2, naive_1x2 = ll, nv
    p = np.array(probs["1X2"])
    y = np.array(outcomes["1X2"])
    by_comp = {}
    for code in CUPS_BY_CODE:
        mask = np.array([c == code for c in comps])
        if mask.any():
            by_comp[code] = {
                "matches": int(mask.sum()),
                "log_loss": round(float(ll_1x2[mask].mean()), 4),
                "naive_log_loss": round(float(naive_1x2[mask].mean()), 4),
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
        log_loss=log_loss,
        hit_rate=round(float((p.argmax(axis=1) == y).mean()), 4),
        announced=round(float(p.max(axis=1).mean()), 4),
        by_competition=by_comp,
        calibration=calib,
        seasons=seasons_out,
    )
