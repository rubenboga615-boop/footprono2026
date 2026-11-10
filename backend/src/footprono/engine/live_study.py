"""Vérification des chances en direct (``engine/live.py``) avant toute publication.

Chaque état de match (score à un repère de temps) est rejoué avec la prévision d'avant-match
**hors échantillon** du moteur ; les chances obtenues sont comparées au résultat final, marché
par marché, par tranches de 10 points (règle de justesse habituelle : au plus ``MAX_GAP``
d'écart dans chaque tranche d'au moins ``MIN_BIN`` sélections).

- Repère « mi-temps » : l'archive (scores à la pause de tous les championnats).
- Repères 15', 30', 60', 75' : minutes des buts et cartons rouges gardées depuis l'étape 1
  (``match_events``), dès qu'il y en a assez.

Les sélections déjà jouées (chance 0 ou 1) ne comptent pas : elles ne disent rien du moteur.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize

from footprono.engine.angles import actual_distribution
from footprono.engine.backtest import Predictions
from footprono.engine.history import History
from footprono.engine.live import (
    ADDED,
    GRID,
    HALF,
    SCORE_EFFECT,
    LiveState,
    evolve,
    live_markets,
)
from footprono.engine.markets import derive_markets
from footprono.engine.scores import MAX_GOALS, MAX_HT_GOALS

FloatArray = NDArray[np.float64]

MIN_BIN = 200
MAX_GAP = 0.03
DECIDED = 0.005  # chance à 0,5 % près de 0 ou 1 : sélection déjà jouée
EPS = 1e-12

# Marchés de fin de match évalués (ceux que les coupons et les paris utilisent le plus).
FAMILIES = {
    "1X2": "Résultat (1X2)",
    "DC": "Double chance",
    "OU": "Buts du match (plus/moins)",
    "BTTS": "Les deux marquent",
    "TEAM_OU_HOME": "Buts d'une équipe",
    "TEAM_OU_AWAY": "Buts d'une équipe",
    "HT_OU": "Buts de la 1re mi-temps",
    "HT_1X2": "Mi-temps : résultat",
}


@dataclass(frozen=True)
class Entry:
    checkpoint: str
    family: str
    probability: float
    won: bool


def _entries(
    checkpoint: str,
    params: tuple[float, float, float, float],
    state: LiveState,
    final: tuple[int, int, int, int],
    effect: Sequence[float] = SCORE_EFFECT,
) -> list[Entry]:
    markets = live_markets(*params, state, effect)
    if markets is None:
        return []
    hg, ag, hht, aht = final
    actual = derive_markets(actual_distribution(hg, ag, hht, aht))
    out = []
    for key, sel in markets.items():
        market = key.split("|", 1)[0]
        if market not in FAMILIES or sel.push or sel.half_win or sel.half_loss:
            continue
        if not DECIDED < sel.win < 1 - DECIDED:
            continue
        out.append(Entry(checkpoint, FAMILIES[market], sel.win, actual[key].win >= 0.999))
    return out


def half_time_rows(
    hist: History, pred: Predictions
) -> list[tuple[float, float, float, float, int, int, int, int]]:
    """(λ dom., λ ext., parts 1re période, score à la pause, score final) de chaque match de
    l'archive dont le score à la pause est connu."""
    out = []
    for k, i in enumerate(pred.row):
        if np.isnan(hist.hht[i]) or np.isnan(hist.aht[i]):
            continue
        out.append((
            pred.lam_h[k], pred.lam_a[k], pred.share_h[k], pred.share_a[k],
            int(hist.hht[i]), int(hist.aht[i]), int(hist.hg[i]), int(hist.ag[i]),
        ))  # fmt: skip
    return out


def half_time_entries(
    rows: Iterable[tuple[float, float, float, float, int, int, int, int]],
    effect: Sequence[float] = SCORE_EFFECT,
) -> list[Entry]:
    """Repère « mi-temps » : chaque match avec son score à la pause."""
    out: list[Entry] = []
    for lh, la, sh, sa, hht, aht, hg, ag in rows:
        if max(hg, ag) > MAX_GOALS or max(hht, aht) > MAX_HT_GOALS:
            continue
        state = LiveState("HT", 45, 0, hht, aht)
        out += _entries("mi-temps", (lh, la, sh, sa), state, (hg, ag, hht, aht), effect)
    return out


def report(entries: Iterable[Entry]) -> dict[str, Any]:
    """Calibration par repère et par famille ; verdict « juste » ou « à revoir »."""
    groups: dict[tuple[str, str], list[Entry]] = defaultdict(list)
    for e in entries:
        groups[(e.checkpoint, e.family)].append(e)
    rows = []
    for (checkpoint, family), items in sorted(groups.items()):
        p = np.array([e.probability for e in items])
        w = np.array([e.won for e in items], dtype=np.float64)
        bins: list[dict[str, Any]] = []
        for b in range(10):
            mask = (p >= b / 10) & (p < (b + 1) / 10)
            n = int(mask.sum())
            if n == 0:
                continue
            bins.append({
                "range": f"{b * 10}-{b * 10 + 10} %", "n": n,
                "announced": round(float(p[mask].mean()), 4),
                "observed": round(float(w[mask].mean()), 4),
            })  # fmt: skip
        checked = [b for b in bins if b["n"] >= MIN_BIN]
        worst = max(
            (abs(float(b["observed"]) - float(b["announced"])) for b in checked), default=None
        )
        loss = -np.mean(w * np.log(p + EPS) + (1 - w) * np.log(1 - p + EPS))
        rows.append({
            "checkpoint": checkpoint, "family": family, "selections": len(items),
            "log_loss": round(float(loss), 4),
            "worst_gap": None if worst is None else round(worst, 4),
            "verdict": "trop peu" if worst is None
            else "juste" if worst <= MAX_GAP else "à revoir",
            "bins": bins,
        })  # fmt: skip
    return {"rows": rows, "rule": {"min_bin": MIN_BIN, "max_gap": MAX_GAP}}


def format_report(rep: dict[str, Any]) -> str:
    lines = []
    for r in rep["rows"]:
        gap = "—" if r["worst_gap"] is None else f"{100 * r['worst_gap']:.1f} pts"
        lines.append(
            f"{r['checkpoint']:9} {r['family']:28} {r['selections']:7d} sélections · "
            f"pire tranche {gap:>8} · {r['verdict']}"
        )
        for b in r["bins"]:
            if b["n"] >= MIN_BIN:
                lines.append(
                    f"    {b['range']:9} n={b['n']:6d} annoncé {100 * b['announced']:5.1f} % "
                    f"arrivé {100 * b['observed']:5.1f} %"
                )
    return "\n".join(lines)


def summarize(entries: Sequence[Entry]) -> str:
    return format_report(report(entries))


# ------------------------------------------------- repères 15', 30', 60', 75' (événements)

CHECKPOINTS = (15, 30, 60, 75)


@dataclass(frozen=True)
class PlayedMatch:
    """Match terminé avec sa prévision d'avant-match et ses événements (étape 1)."""

    params: tuple[float, float, float, float]  # λ dom., λ ext., part 1re période dom. / ext.
    goals: tuple[tuple[int, int, str], ...]  # (minute, temps additionnel, "home" / "away")
    reds: tuple[tuple[int, int, str], ...]
    final: tuple[int, int, int, int]  # score final, score à la pause


def _before(minute: int, extra: int, checkpoint: int) -> bool:
    """L'événement a eu lieu avant le repère (temps additionnel de la 1re période compris
    avant un repère de 2e période)."""
    del extra
    return minute < checkpoint


def consistent(m: PlayedMatch) -> bool:
    """Buts des événements = score final (et score à la pause) : sinon le match est écarté."""
    hg, ag, hht, aht = m.final
    home = sum(1 for _, _, s in m.goals if s == "home")
    first = [s for minute, _, s in m.goals if minute <= 45]
    return (
        home == hg
        and len(m.goals) - home == ag
        and first.count("home") == hht
        and first.count("away") == aht
    )


def minute_entries(matches: Iterable[PlayedMatch]) -> list[Entry]:
    out: list[Entry] = []
    for m in matches:
        if not consistent(m):
            continue
        hg, ag, hht, aht = m.final
        if max(hg, ag) > MAX_GOALS or max(hht, aht) > MAX_HT_GOALS:
            continue
        for checkpoint in CHECKPOINTS:
            if any(_before(minute, extra, checkpoint) for minute, extra, _ in m.reds):
                continue  # carton rouge : pas de chance calculée
            scored = [s for minute, extra, s in m.goals if _before(minute, extra, checkpoint)]
            status = "1H" if checkpoint <= 45 else "2H"
            state = LiveState(
                status, checkpoint, 0, scored.count("home"), scored.count("away"),
                ht_home=hht, ht_away=aht,
            )  # fmt: skip
            out += _entries(f"{checkpoint}'", m.params, state, m.final)
    return out


# ------------------------------------------------------- effet du score (apprentissage)


def fit_score_effect(
    rows: Sequence[tuple[float, float, float, float, int, int, int, int]],
) -> tuple[float, ...]:
    """Effet du score (``engine.live.SCORE_EFFECT``) qui explique le mieux les scores finaux
    sachant le score à la pause : vraisemblance de la 2e période déroulée minute par minute.
    ``rows`` : (λ dom., λ ext., part 1re période dom., ext., pause dom., ext., final dom.,
    ext.)."""
    keep = [r for r in rows if max(r[6], r[7]) <= MAX_GOALS and max(r[4], r[5]) <= MAX_HT_GOALS]
    n = len(keep)
    length = HALF + ADDED[1]
    start = np.zeros((n, GRID, GRID))
    idx = np.arange(n)
    hht = np.array([r[4] for r in keep])
    aht = np.array([r[5] for r in keep])
    hg = np.array([r[6] for r in keep])
    ag = np.array([r[7] for r in keep])
    start[idx, hht, aht] = 1.0
    rate_h = np.array([(1 - r[2]) * r[0] / length for r in keep])
    rate_a = np.array([(1 - r[3]) * r[1] / length for r in keep])

    def loss(theta: FloatArray) -> float:
        p = evolve(start, rate_h, rate_a, length, tuple(np.exp(theta)))
        return float(-np.log(p[idx, hg, ag] + EPS).sum())

    res = minimize(loss, np.zeros(5), method="L-BFGS-B", bounds=[(-1.0, 1.0)] * 5)
    return tuple(round(float(x), 4) for x in np.exp(res.x))
