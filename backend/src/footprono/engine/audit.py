"""Audit de tous les marchés proposés par l'application.

Chaque marché « à deux issues » (gagné ou perdu, sans remboursement) que le
moteur produit est évalué hors échantillon, famille par famille :

- **gain sur la référence naïve** (log loss) : la référence est la fréquence
  de la même issue dans le même championnat sur les saisons précédentes
  (causale) ; une famille dont le moteur ne fait pas mieux n'apporte rien à
  l'utilisateur ;
- **calibration** : courbe annoncé / observé par tranches de 10 points ; une
  tranche (d'au moins ``MIN_BIN`` sélections) qui s'écarte de plus de
  ``ALERT_SE`` erreurs types signale une famille à corriger.

Les sélections d'un même match ne sont pas indépendantes (« +1,5 » et
« +2,5 » buts, « clean sheet » et « gagner sans encaisser ») : les erreurs
types sont calculées par match (écarts d'un match additionnés), sinon elles
sont sous-estimées et donnent de fausses alertes.

Verdict par famille : **validé** (meilleur que la référence et bien
calibré), **à corriger** (meilleur que la référence, calibration à revoir),
**sans apport** (pas mieux que la fréquence du championnat).

Exclus : les marchés avec remboursement (remboursé si nul, handicap
asiatique à ligne entière ou quart de but, évalué ailleurs face aux cotes)
et les points de cartons (modèles jaunes / rouges séparés, non évalués ici).
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from footprono.engine.angles import actual_distribution
from footprono.engine.backtest import Predictions
from footprono.engine.counts import (
    CountsConfig,
    count_markets,
    count_values,
    fit_counts,
)
from footprono.engine.history import History
from footprono.engine.markets import derive_markets
from footprono.engine.scores import MAX_GOALS, MAX_HT_GOALS, score_distribution

NAIVE_SEASONS = 3
EPS = 1e-12
MIN_BIN = 200
ALERT_SE = 3.5  # environ 200 tranches testées : seuil plus strict que la calibration

FAMILIES = {
    "1X2": "Résultat (1X2)",
    "DC": "Double chance",
    "OU": "Buts du match (plus/moins)",
    "TEAM_OU_HOME": "Buts d'une équipe",
    "TEAM_OU_AWAY": "Buts d'une équipe",
    "BTTS": "Les deux marquent",
    "CS": "Score exact",
    "CLEAN_SHEET": "Clean sheet",
    "WIN_TO_NIL": "Gagner sans encaisser",
    "MARGIN": "Écart de buts",
    "ODD_EVEN": "Total pair / impair",
    "AH": "Handicap asiatique (lignes x,5)",
    "EH": "Handicap européen",
    "1X2_OU": "Combiné résultat + buts",
    "1X2_BTTS": "Combiné résultat + les deux marquent",
    "OU_BTTS": "Combiné buts + les deux marquent",
    "HT_1X2": "Mi-temps : résultat",
    "HT_OU": "Mi-temps : buts",
    "HT_BTTS": "Mi-temps : les deux marquent",
    "HTFT": "Mi-temps / fin de match",
    "HIGHEST_HALF": "Mi-temps la plus prolifique",
}
HALF_TIME = ("HT_", "HTFT", "HIGHEST_HALF")
COUNT_LABELS = {"CORNERS": "Corners", "CARDS": "Cartons", "SHOTS": "Tirs", "SOT": "Tirs cadrés"}
COUNT_KINDS = {
    "_OU": "total",
    "_TEAM_OU_HOME": "par équipe",
    "_TEAM_OU_AWAY": "par équipe",
    "_1X2": "le plus de",
    "_AH": "handicap",
}


@dataclass(frozen=True)
class Entry:
    match: int  # identifiant du match (regroupement des erreurs types)
    competition: str
    season: int
    key: str
    probability: float
    won: int


def family_of(key: str) -> str:
    market = key.split("|", 1)[0]
    if market in FAMILIES:
        return FAMILIES[market]
    for prefix, label in COUNT_LABELS.items():
        for suffix, kind in COUNT_KINDS.items():
            if market == prefix + suffix:
                return f"{label} : {kind}"
    return market


def _binary(sel: Any) -> bool:
    return not (sel.push or sel.half_win or sel.half_loss)


def _goal_outcomes(hist: History, i: int) -> dict[str, int] | None:
    hg, ag = hist.hg[i], hist.ag[i]
    if np.isnan(hg) or np.isnan(ag) or max(hg, ag) > MAX_GOALS:
        return None
    has_ht = not (np.isnan(hist.hht[i]) or np.isnan(hist.aht[i]))
    hht, aht = (int(hist.hht[i]), int(hist.aht[i])) if has_ht else (0, 0)
    if max(hht, aht) > MAX_HT_GOALS:
        return None
    actual = derive_markets(actual_distribution(int(hg), int(ag), hht, aht))
    return {
        k: int(s.win >= 0.999)
        for k, s in actual.items()
        if k.split("|", 1)[0] in FAMILIES
        and (has_ht or not k.startswith(HALF_TIME))
        and not (
            k.startswith("AH|")
            and float(k.split("|")[1]) % 1 != 0.5
            and float(k.split("|")[1]) % 1 != -0.5
        )
    }


def goal_entries(hist: History, pred: Predictions) -> list[Entry]:
    out = []
    for k in range(len(pred.row)):
        i = pred.row[k]
        outcomes = _goal_outcomes(hist, i)
        if outcomes is None:
            continue
        model = derive_markets(
            score_distribution(
                pred.lam_h[k], pred.lam_a[k], pred.rho[k], pred.share_h[k], pred.share_a[k]
            )
        )
        for key, won in outcomes.items():
            sel = model[key]
            if _binary(sel):
                out.append(Entry(i, pred.competition[k], pred.season[k], key, sel.win, won))
    return out


def goal_history(hist: History, competitions: Sequence[str], seasons: Sequence[int]) -> list[Entry]:
    """Issues réelles des saisons précédentes (référence naïve)."""
    rows = np.where(
        np.isin(hist.competition, list(competitions))
        & (hist.season >= min(seasons) - NAIVE_SEASONS)
        & (hist.season < max(seasons))
        & hist.finished
        & ~hist.excluded
    )[0]
    out = []
    for i in rows:
        outcomes = _goal_outcomes(hist, int(i))
        for key, won in (outcomes or {}).items():
            out.append(Entry(int(i), str(hist.competition[i]), int(hist.season[i]), key, 0.0, won))
    return out


def _onehot(h: int, a: int) -> np.ndarray:
    joint = np.zeros((h + 1, a + 1))
    joint[h, a] = 1.0
    return joint


def count_entries(
    hist: History,
    competitions: Sequence[str],
    seasons: Sequence[int],
    stat: str,
    cfg: CountsConfig,
    refit_every_days: int = 7,
) -> tuple[list[Entry], list[Entry]]:
    """(prévisions hors échantillon, issues des saisons précédentes) d'une statistique."""
    yh, ya = count_values(hist, stat)
    entries: list[Entry] = []
    for comp in competitions:
        test = np.where(
            (hist.competition == comp)
            & np.isin(hist.season, list(seasons))
            & hist.finished
            & ~hist.excluded
            & ~np.isnan(yh)
            & ~np.isnan(ya)
        )[0]
        test = test[np.argsort(hist.date[test], kind="stable")]
        fitted_on: np.datetime64 | None = None
        model = None
        for i in test:
            day = hist.date[i]
            if fitted_on is None or day >= fitted_on + np.timedelta64(refit_every_days, "D"):
                model = fit_counts(hist, comp, stat, day, cfg)
                fitted_on = day
            assert model is not None
            ref = str(hist.referee[i]) if len(hist.referee) else ""
            mh, ma = model.means(int(hist.home[i]), int(hist.away[i]), ref)
            markets = count_markets(stat, model.joint(mh, ma))
            actual = count_markets(stat, _onehot(int(yh[i]), int(ya[i])))
            for key, sel in markets.items():
                entries.append(
                    Entry(
                        int(i),
                        comp,
                        int(hist.season[i]),
                        key,
                        sel.win,
                        int(actual[key].win >= 0.999),
                    )
                )
    past_rows = np.where(
        np.isin(hist.competition, list(competitions))
        & (hist.season >= min(seasons) - NAIVE_SEASONS)
        & (hist.season < max(seasons))
        & hist.finished
        & ~hist.excluded
        & ~np.isnan(yh)
        & ~np.isnan(ya)
    )[0]
    past = []
    for i in past_rows:
        for key, sel in count_markets(stat, _onehot(int(yh[i]), int(ya[i]))).items():
            past.append(
                Entry(
                    int(i),
                    str(hist.competition[i]),
                    int(hist.season[i]),
                    key,
                    0.0,
                    int(sel.win >= 0.999),
                )
            )
    return entries, past


def _naive_lookup(past: Iterable[Entry]) -> dict[tuple[str, int, str], tuple[int, int]]:
    counts: dict[tuple[str, int, str], list[int]] = defaultdict(lambda: [0, 0])
    for e in past:
        c = counts[(e.competition, e.season, e.key)]
        c[0] += e.won
        c[1] += 1
    return {k: (v[0], v[1]) for k, v in counts.items()}


def audit_report(entries: Sequence[Entry], past: Iterable[Entry]) -> dict[str, Any]:
    lookup = _naive_lookup(past)

    def naive(e: Entry) -> float | None:
        won = n = 0
        for s in range(e.season - NAIVE_SEASONS, e.season):
            w, k = lookup.get((e.competition, s, e.key), (0, 0))
            won += w
            n += k
        return (won + 1) / (n + 2) if n else None

    by_family: dict[str, list[tuple[Entry, float | None]]] = defaultdict(list)
    for e in entries:
        by_family[family_of(e.key)].append((e, naive(e)))
    families = {}
    for fam, items in sorted(by_family.items()):
        families[fam] = _family_metrics(items)
    return {"families": families}


def _family_metrics(items: Sequence[tuple[Entry, float | None]]) -> dict[str, Any]:
    p = np.clip(np.array([e.probability for e, _ in items]), EPS, 1 - EPS)
    y = np.array([e.won for e, _ in items], dtype=np.float64)
    ll = -(y * np.log(p) + (1 - y) * np.log(1 - p))
    has_naive = np.array([q is not None for _, q in items])
    q = np.clip(np.array([q if q is not None else 0.5 for _, q in items]), EPS, 1 - EPS)
    nll = -(y * np.log(q) + (1 - y) * np.log(1 - q))
    matches = np.array([e.match for e, _ in items])
    # Gain par match (somme sur les sélections du match) : erreur type prudente.
    diff: dict[int, float] = defaultdict(float)
    for m, d in zip(matches[has_naive], (nll - ll)[has_naive], strict=True):
        diff[int(m)] += float(d)
    per_match = np.array(list(diff.values()))
    n_sel = int(has_naive.sum())
    gain = float(per_match.sum() / n_sel) if n_sel else float("nan")
    gain_se = (
        float(per_match.std() * np.sqrt(len(per_match)) / n_sel) if n_sel > 1 else float("nan")
    )
    curve, worst = [], None
    for b in range(10):
        lo, hi = b / 10, (b + 1) / 10
        mask = (p >= lo) & ((p < hi) if b < 9 else (p <= hi))
        if mask.sum() == 0:
            continue
        pm, ym = p[mask], y[mask]
        # Erreur type par match (les sélections d'un même match sont liées) :
        # somme des écarts du match, au carré.
        by_match: dict[int, float] = defaultdict(float)
        for m, r in zip(matches[mask], ym - pm, strict=True):
            by_match[int(m)] += float(r)
        se = float(np.sqrt(np.sum(np.square(list(by_match.values())))) / mask.sum())
        gap = float(ym.mean() - pm.mean())
        row = {
            "from": lo, "to": hi, "n": int(mask.sum()),
            "announced": round(float(pm.mean()), 4), "observed": round(float(ym.mean()), 4),
            "gap": round(gap, 4), "se": round(se, 4),
        }  # fmt: skip
        curve.append(row)
        alert = mask.sum() >= MIN_BIN and abs(gap) > ALERT_SE * se
        if alert and (worst is None or abs(gap) > abs(worst["gap"])):
            worst = row
    naive_ll = float(nll[has_naive].mean()) if n_sel else float("nan")
    skill = 1 - float(ll[has_naive].mean()) / naive_ll if n_sel else float("nan")
    if n_sel and gain - 2 * gain_se <= 0:
        verdict = "sans apport"
    elif worst is not None:
        verdict = "à corriger"
    else:
        verdict = "validé"
    return {
        "selections": len(items),
        "markets": len({e.key for e, _ in items}),
        "matches": len(set(matches.tolist())),
        "log_loss": round(float(ll.mean()), 4),
        "naive_log_loss": round(naive_ll, 4),
        "skill": round(skill, 4),
        "gain": round(gain, 5),
        "gain_two_se": round(2 * gain_se, 5),
        "brier": round(float(np.mean((p - y) ** 2)), 4),
        "worst_bin": worst,
        "curve": curve,
        "verdict": verdict,
    }


def format_audit(report: dict[str, Any]) -> str:
    lines = [
        "Audit de tous les marchés (hors échantillon)",
        "skill = part de la log loss naïve gagnée (positif = mieux) ; pire tranche = écart",
        f"observé - annoncé au-delà de {ALERT_SE:g} erreurs types (tranches d'au moins {MIN_BIN}).",
        "",
        f"{'Famille':<38}{'marchés':>8}{'sélections':>11}{'skill':>8}  "
        f"{'verdict':<12} pire tranche",
    ]
    order = {"validé": 0, "à corriger": 1, "sans apport": 2}
    for fam, m in sorted(
        report["families"].items(), key=lambda kv: (order[kv[1]["verdict"]], kv[0])
    ):
        w = m["worst_bin"]
        worst = (
            f"{w['from']:.0%}-{w['to']:.0%} : annoncé {w['announced']:.1%}, "
            f"observé {w['observed']:.1%}"
            if w
            else "—"
        )
        lines.append(
            f"{fam:<38}{m['markets']:>8}{m['selections']:>11}{m['skill']:>+8.1%}  "
            f"{m['verdict']:<12} {worst}"
        )
    return "\n".join(lines)
