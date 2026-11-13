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
    BUCKET,
    BUCKETS,
    DEFAULT_MODEL,
    GRID,
    HALF,
    PHASES,
    LiveModel,
    LiveState,
    evolve,
    live_markets,
    phase_of,
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
    model: LiveModel = DEFAULT_MODEL,
) -> list[Entry]:
    markets = live_markets(*params, state, model)
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
    model: LiveModel = DEFAULT_MODEL,
) -> list[Entry]:
    """Repère « mi-temps » : chaque match avec son score à la pause."""
    out: list[Entry] = []
    for lh, la, sh, sa, hht, aht, hg, ag in rows:
        if max(hg, ag) > MAX_GOALS or max(hht, aht) > MAX_HT_GOALS:
            continue
        state = LiveState("HT", 45, 0, hht, aht)
        out += _entries("mi-temps", (lh, la, sh, sa), state, (hg, ag, hht, aht), model)
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
        # Règle validée le 06/11/2026 (sélections nationales), reprise le 11/11/2026 pour le
        # direct : chaque tranche à 3 points près ou dans deux erreurs types (le hasard).
        wrong = [b for b in checked if not _within(b)]
        loss = -np.mean(w * np.log(p + EPS) + (1 - w) * np.log(1 - p + EPS))
        rows.append({
            "checkpoint": checkpoint, "family": family, "selections": len(items),
            "log_loss": round(float(loss), 4),
            "worst_gap": None if worst is None else round(worst, 4),
            "verdict": "trop peu" if worst is None else "à revoir" if wrong else "juste",
            "bins": bins,
        })  # fmt: skip
    return {"rows": rows, "rule": {"min_bin": MIN_BIN, "max_gap": MAX_GAP, "two_se": True}}


def _within(b: dict[str, Any]) -> bool:
    """Tranche juste : à ``MAX_GAP`` près, ou dans deux erreurs types de l'annoncé."""
    a, o, n = float(b["announced"]), float(b["observed"]), int(b["n"])
    gap = abs(o - a)
    return gap <= MAX_GAP or gap <= 2 * float(np.sqrt(a * (1 - a) / n))


# Marché d'une clé « marché|ligne|sélection », pour retirer une famille fautive du direct.
def family_of_key(key: str) -> str | None:
    return FAMILIES.get(key.split("|", 1)[0])


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

CHECKPOINTS: tuple[int | str, ...] = (15, 30, "mi-temps", 60, 75)


@dataclass(frozen=True)
class PlayedMatch:
    """Match terminé avec sa prévision d'avant-match et ses événements (étape 1)."""

    params: tuple[float, float, float, float]  # λ dom., λ ext., part 1re période dom. / ext.
    goals: tuple[tuple[int, int, str], ...]  # (minute, temps additionnel, "home" / "away")
    reds: tuple[tuple[int, int, str], ...]
    final: tuple[int, int, int, int]  # score final, score à la pause


def _before(minute: int, extra: int, checkpoint: int) -> bool:
    """L'événement a eu lieu avant la fin de la minute du repère (« 30' » : 30 minutes
    jouées ; un but de la 30e minute est déjà marqué). Temps additionnel de la 1re période
    compris avant un repère de 2e période."""
    del extra
    return minute <= checkpoint


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


def minute_entries(matches: Iterable[PlayedMatch], model: LiveModel = DEFAULT_MODEL) -> list[Entry]:
    out: list[Entry] = []
    for m in matches:
        if not consistent(m):
            continue
        hg, ag, hht, aht = m.final
        if max(hg, ag) > MAX_GOALS or max(hht, aht) > MAX_HT_GOALS:
            continue
        for checkpoint in CHECKPOINTS:
            if checkpoint == "mi-temps":
                if any(minute <= HALF for minute, _, _ in m.reds):
                    continue
                state = LiveState("HT", HALF, 0, hht, aht)
                out += _entries("mi-temps", m.params, state, m.final, model)
                continue
            assert isinstance(checkpoint, int)
            if any(_before(minute, extra, checkpoint) for minute, extra, _ in m.reds):
                continue  # carton rouge : pas de chance calculée
            scored = [s for minute, extra, s in m.goals if _before(minute, extra, checkpoint)]
            status = "1H" if checkpoint <= HALF else "2H"
            state = LiveState(
                status, checkpoint, 0, scored.count("home"), scored.count("away"),
                ht_home=hht, ht_away=aht,
            )  # fmt: skip
            out += _entries(f"{checkpoint}'", m.params, state, m.final, model)
    return out


# ---------------------------------- rythme des buts et effet du score (apprentissage)


def _unit(minute: int, extra: int, half: int) -> int:
    """Minute d'un but dans sa période : 1 à 45, puis 46 et suivantes pour le temps
    additionnel (au plus le temps additionnel moyen arrondi)."""
    added = int(np.ceil(ADDED[half]))
    base = minute if half == 0 else minute - HALF
    if extra > 0 or base > HALF:
        return HALF + min(max(extra, base - HALF, 1), added)
    return min(max(base, 1), HALF)


def fit_live_model(matches: Iterable[PlayedMatch], rounds: int = 60) -> LiveModel:
    """Rythme des buts par tranche de 5 minutes (et temps additionnel) de chaque période, et
    effet du score, appris sur les minutes des buts. Modèle de Poisson multiplicatif : buts
    d'une équipe dans une minute = rythme de base, fois la tranche, fois l'effet du score du
    moment, propre à chaque moment du match (1re période, 46-60', 61-75', 76' à la fin).
    Ajusté par itérations proportionnelles ; un match compte jusqu'à son premier carton
    rouge."""
    goals = np.zeros((2, BUCKETS + 1, 5))
    exposure = np.zeros((2, BUCKETS + 1, 5))
    for m in matches:
        if not consistent(m):
            continue
        lh, la, sh, sa = m.params
        red = min((minute for minute, _, _ in m.reds), default=10_000)
        by_unit: dict[tuple[int, int], list[str]] = defaultdict(list)
        for minute, extra, side in m.goals:
            half = 0 if minute <= HALF else 1
            by_unit[(half, _unit(minute, extra, half))].append(side)
        home = away = 0
        for half in (0, 1):
            length = HALF + ADDED[half]
            share_h, share_a = (sh, sa) if half == 0 else (1 - sh, 1 - sa)
            base_h, base_a = share_h * lh / length, share_a * la / length
            for unit in range(1, HALF + int(np.ceil(ADDED[half])) + 1):
                clock = unit + (0 if half == 0 else HALF)
                if clock >= red:
                    break
                bucket = BUCKETS if unit > HALF else (unit - 1) // BUCKET
                dh = int(np.clip(home - away, -2, 2)) + 2
                da = int(np.clip(away - home, -2, 2)) + 2
                exposure[half, bucket, dh] += base_h
                exposure[half, bucket, da] += base_a
                for side in by_unit.get((half, unit), []):
                    if side == "home":
                        goals[half, bucket, dh] += 1
                        home += 1
                    else:
                        goals[half, bucket, da] += 1
                        away += 1
            if any(minute <= HALF for minute, _, _ in m.reds) and half == 0:
                break
    # Moment du match de chaque tranche (effet du score propre à chaque moment).
    phase = np.array(
        [[phase_of(half, min(5 * b + 1, HALF + 1)) for b in range(BUCKETS + 1)] for half in (0, 1)]
    )
    rhythm = np.ones((2, BUCKETS + 1))
    effect = np.ones((PHASES, 5))
    for _ in range(rounds):
        rhythm = goals.sum(axis=2) / np.maximum((exposure * effect[phase]).sum(axis=2), EPS)
        for ph in range(PHASES):
            cells = phase == ph
            g = goals[cells].sum(axis=0)
            e = (exposure[cells] * rhythm[cells][:, None]).sum(axis=0)
            effect[ph] = np.where(e > 0, g / np.maximum(e, EPS), 1.0)
            # Échelle portée par le rythme : effet 1 à égalité.
            scale = effect[ph, 2] if effect[ph, 2] > 0 else 1.0
            rhythm[cells] *= scale
            effect[ph] /= scale
    return LiveModel(
        first=tuple(round(float(x), 4) for x in rhythm[0]),
        second=tuple(round(float(x), 4) for x in rhythm[1]),
        effect=tuple(round(float(x), 4) for x in effect.ravel()),
    )


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


# ------------------------------------------- coupons à la mi-temps (plan, étape 8)

# Mêmes tranches que le Coupon intelligent (bookmaker/smart_coupon.py) : Sûr vise 83,5 %.
HALF_TIME_PROFILES = {
    "Sûr": (0.75, 0.92, 0.835),
    "Équilibré": (0.60, 0.75, None),
    "Audacieux": (0.45, 0.60, None),
}


def half_time_angles(
    rows: Iterable[tuple[float, float, float, float, int, int, int, int]],
    model: LiveModel = DEFAULT_MODEL,
    coupon_size: int = 3,
) -> dict[str, Any]:
    """À la pause, la sélection de chaque match choisie comme le Coupon intelligent (la plus
    probable de la tranche, ou la plus proche de la cible pour Sûr) : chance annoncée et
    arrivée, par profil et par marché ; puis des coupons de ``coupon_size`` sélections de
    matchs différents pris dans l'ordre (annoncé = produit des chances)."""
    picks: dict[str, list[Entry]] = {name: [] for name in HALF_TIME_PROFILES}
    for lh, la, sh, sa, hht, aht, hg, ag in rows:
        if max(hg, ag) > MAX_GOALS or max(hht, aht) > MAX_HT_GOALS:
            continue
        entries = _entries(
            "mi-temps",
            (lh, la, sh, sa),
            LiveState("HT", 45, 0, hht, aht),
            (hg, ag, hht, aht),
            model,
        )
        entries = [e for e in entries if not e.family.startswith(("Buts de la 1re", "Mi-temps"))]
        for name, (low, high, target) in HALF_TIME_PROFILES.items():
            inside = [e for e in entries if low <= e.probability < high]
            if not inside:
                continue
            if target is None:
                best = max(inside, key=lambda e: e.probability)
            else:
                best = min(inside, key=lambda e: (abs(e.probability - target), -e.probability))
            picks[name].append(best)

    def summary(items: Sequence[Entry]) -> dict[str, Any]:
        n = len(items)
        if n == 0:
            return {"n": 0}
        p = np.array([e.probability for e in items])
        w = np.array([e.won for e in items], dtype=np.float64)
        return {
            "n": n,
            "announced": round(float(p.mean()), 4),
            "observed": round(float(w.mean()), 4),
            "two_se": round(float(2 * np.sqrt(np.sum(p * (1 - p))) / n), 4),
        }

    out: dict[str, Any] = {}
    for name, items in picks.items():
        by_family: dict[str, list[Entry]] = defaultdict(list)
        for e in items:
            by_family[e.family].append(e)
        coupons = [
            items[i : i + coupon_size] for i in range(0, len(items) - coupon_size + 1, coupon_size)
        ]
        cp = np.array([float(np.prod([e.probability for e in c])) for c in coupons])
        cw = np.array([all(e.won for e in c) for c in coupons], dtype=np.float64)
        out[name] = {
            "selections": summary(items),
            "families": {
                fam: summary(v) for fam, v in sorted(by_family.items(), key=lambda kv: -len(kv[1]))
            },
            "coupons": {
                "size": coupon_size,
                "n": len(coupons),
                "announced": round(float(cp.mean()), 4) if len(cp) else None,
                "observed": round(float(cw.mean()), 4) if len(cw) else None,
                "two_se": round(float(2 * np.sqrt(np.sum(cp * (1 - cp))) / len(cp)), 4)
                if len(cp)
                else None,
            },
        }
    return out


def refine_second_half(
    model: LiveModel, matches: Sequence[PlayedMatch], sample: int = 8000, seed: int = 1
) -> LiveModel:
    """Effet du score de la 2e période affiné sur ce que l'on vérifie : la vraisemblance du
    score final sachant le score à la mi-temps, à 60' et à 75' (apprentissage du 11/11/2026 :
    appris minute par minute, l'équipe menée d'un but était sous-estimée, menée 1,03 à 1,15 ;
    affiné sur le score final, 1,17, et la mi-temps 2025 devient juste). Mêmes 4 valeurs
    (mené de 2+, mené de 1, devant de 1, devant de 2+) pour toute la 2e période ; la 1re
    période et le rythme ne changent pas."""
    rng = np.random.default_rng(seed)
    keep = [m for m in matches if consistent(m) and max(m.final[0], m.final[1]) <= MAX_GOALS]
    if len(keep) > sample:
        keep = [keep[i] for i in rng.choice(len(keep), sample, replace=False)]
    if not keep:
        return model
    length = HALF + ADDED[1]
    groups = []
    for played in (0, 15, 30):  # mi-temps, 60', 75'
        rows = []
        for m in keep:
            clock = HALF + played
            if any(minute <= clock for minute, _, _ in m.reds):
                continue
            scored = [s for minute, _, s in m.goals if minute <= clock]
            lh, la, sh, sa = m.params
            rows.append((
                scored.count("home"), scored.count("away"), m.final[0], m.final[1],
                (1 - sh) * lh / length, (1 - sa) * la / length,
            ))  # fmt: skip
        if not rows:
            continue
        arr = np.array(rows, dtype=np.float64)
        n = len(rows)
        start = np.zeros((n, GRID, GRID))
        start[np.arange(n), arr[:, 0].astype(int), arr[:, 1].astype(int)] = 1.0
        groups.append((played, start, arr))
    base = list(model.effect if len(model.effect) == 5 * PHASES else model.effect * PHASES)
    free = (0, 1, 3, 4)

    def with_effect(theta: FloatArray) -> LiveModel:
        e = list(base)
        for ph in (1, 2, 3):
            for i, t in zip(free, theta, strict=True):
                e[5 * ph + i] = float(np.exp(t))
        return LiveModel(first=model.first, second=model.second, effect=tuple(e))

    def loss(theta: FloatArray) -> float:
        m = with_effect(theta)
        total = 0.0
        for played, start, arr in groups:
            profile, effects = m.steps(1, played, 0)
            p = evolve(start, arr[:, 4], arr[:, 5], 0, profile=profile, effects=effects)
            idx = np.arange(len(arr))
            total -= float(np.log(p[idx, arr[:, 2].astype(int), arr[:, 3].astype(int)] + EPS).sum())
        return total

    x0 = np.log(np.array([base[5 * 3 + i] for i in free]))
    res = minimize(loss, x0, method="L-BFGS-B", bounds=[(-0.7, 0.7)] * len(free),
                   options={"maxiter": 30})  # fmt: skip
    refined = with_effect(res.x)
    return LiveModel(
        first=refined.first,
        second=refined.second,
        effect=tuple(round(x, 4) for x in refined.effect),
    )


# ------------------------------- coupons proposés pendant le match (mi-temps, 60', 75')

COUPON_MOMENTS: tuple[int | str, ...] = ("mi-temps", 60, 75)


def state_at(m: PlayedMatch, moment: int | str) -> LiveState | None:
    """État du match au moment donné (« mi-temps », 60, 75) ; None après un carton rouge
    (pas de chance calculée) ou pour un match écarté."""
    if not consistent(m):
        return None
    hg, ag, hht, aht = m.final
    if max(hg, ag) > MAX_GOALS or max(hht, aht) > MAX_HT_GOALS:
        return None
    if moment == "mi-temps":
        if any(minute <= HALF for minute, _, _ in m.reds):
            return None
        return LiveState("HT", HALF, 0, hht, aht)
    assert isinstance(moment, int)
    if any(_before(minute, extra, moment) for minute, extra, _ in m.reds):
        return None
    scored = [s for minute, extra, s in m.goals if _before(minute, extra, moment)]
    status = "1H" if moment <= HALF else "2H"
    return LiveState(
        status, moment, 0, scored.count("home"), scored.count("away"), ht_home=hht, ht_away=aht
    )


def _summary(probabilities: Sequence[float], won: Sequence[bool]) -> dict[str, Any]:
    n = len(probabilities)
    if n == 0:
        return {"n": 0, "verdict": "trop peu"}
    p = np.array(probabilities, dtype=np.float64)
    w = np.array(won, dtype=np.float64)
    announced, observed = float(p.mean()), float(w.mean())
    two_se = float(2 * np.sqrt(np.sum(p * (1 - p))) / n)
    gap = abs(observed - announced)
    verdict = (
        "trop peu" if n < MIN_BIN else "juste" if gap <= MAX_GAP or gap <= two_se else "à revoir"
    )
    return {
        "n": n,
        "announced": round(announced, 4),
        "observed": round(observed, 4),
        "two_se": round(two_se, 4),
        "verdict": verdict,
    }


def coupon_angles(
    matches: Iterable[PlayedMatch],
    moment: int | str,
    model: LiveModel = DEFAULT_MODEL,
    banned: Iterable[str] = (),
    sizes: Sequence[int] = (2, 3),
) -> dict[str, Any]:
    """Coupons proposés à un moment du match (« mi-temps », 60', 75'), choisis comme le
    Coupon intelligent : pour chaque match, la sélection de chaque profil (Sûr, Équilibré,
    Audacieux) ; chance annoncée contre arrivée, par profil et par marché ; puis des combinés
    de ``sizes`` sélections de matchs différents (une sélection par match, annoncé = produit
    des chances). Marchés de la 1re mi-temps et marchés retirés (``banned``) jamais proposés.
    Règle : 3 points près ou deux erreurs types, comme les chances en direct."""
    label = moment if isinstance(moment, str) else f"{moment}'"
    banned = set(banned)
    picks: dict[str, list[Entry]] = {name: [] for name in HALF_TIME_PROFILES}
    for m in matches:
        state = state_at(m, moment)
        if state is None:
            continue
        entries = [
            e
            for e in _entries(label, m.params, state, m.final, model)
            if not e.family.startswith(("Buts de la 1re", "Mi-temps")) and e.family not in banned
        ]
        for name, (low, high, target) in HALF_TIME_PROFILES.items():
            inside = [e for e in entries if low <= e.probability < high]
            if not inside:
                continue
            if target is None:
                best = max(inside, key=lambda e: e.probability)
            else:
                best = min(inside, key=lambda e: (abs(e.probability - target), -e.probability))
            picks[name].append(best)
    out: dict[str, Any] = {"moment": label, "profiles": {}}
    for name, items in picks.items():
        by_family: dict[str, list[Entry]] = defaultdict(list)
        for e in items:
            by_family[e.family].append(e)
        combos = {}
        for size in sizes:
            groups = [items[i : i + size] for i in range(0, len(items) - size + 1, size)]
            combos[str(size)] = _summary(
                [float(np.prod([e.probability for e in g])) for g in groups],
                [all(e.won for e in g) for g in groups],
            )
        out["profiles"][name] = {
            "selections": _summary([e.probability for e in items], [e.won for e in items]),
            "families": {
                fam: _summary([e.probability for e in v], [e.won for e in v])
                for fam, v in sorted(by_family.items(), key=lambda kv: -len(kv[1]))
            },
            "combos": combos,
        }
    checked = [
        s
        for p in out["profiles"].values()
        for s in (p["selections"], *p["combos"].values())
        if s["verdict"] != "trop peu"
    ]
    out["verdict"] = (
        "trop peu"
        if not checked
        else "à revoir"
        if any(s["verdict"] == "à revoir" for s in checked)
        else "juste"
    )
    return out
