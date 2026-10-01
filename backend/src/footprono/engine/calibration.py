"""Calibration détaillée : chaque marché, par championnat et par saison.

Une moyenne globale juste peut cacher un championnat mal prédit, une saison
qui dérive ou un marché mal calibré. Pour chaque marché suivi, sur les
prévisions hors échantillon du backtest :

- **log loss** et **score de Brier** du moteur, comparés à une **référence
  naïve causale** : fréquence de l'issue dans le même championnat sur les
  ``NAIVE_SEASONS`` saisons précédentes (rien de postérieur à la saison testée) ;
- **calibration** : probabilité annoncée moyenne contre fréquence observée,
  avec l'erreur type de l'écart (si l'annonce était juste) ;
- **courbe de calibration** par tranches de 10 points ;
- **alertes** : cases (championnat, saison) dont l'écart dépasse 3 erreurs
  types (seuil large : avec des centaines de cases, 2 erreurs types
  donneraient des fausses alertes par simple hasard).

Corners et cartons : plus/moins à la ligne d'évaluation de ``counts_backtest``
(avec l'arbitre), référence naïve de ce module (distribution des totaux du
championnat sur la fenêtre d'apprentissage).
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np

from footprono.engine.angles import actual_distribution
from footprono.engine.backtest import Predictions
from footprono.engine.history import History
from footprono.engine.markets import derive_markets
from footprono.engine.scores import MAX_GOALS, MAX_HT_GOALS, score_distribution

# Marchés de buts suivis (une issue par marché à deux issues : l'autre est son complément).
GOAL_GROUPS = {
    "1X2||home": "1X2 : domicile",
    "1X2||draw": "1X2 : nul",
    "1X2||away": "1X2 : extérieur",
    "DC||1X": "Double chance 1X",
    "DC||X2": "Double chance X2",
    "OU|1.5|over": "+1,5 buts",
    "OU|2.5|over": "+2,5 buts",
    "OU|3.5|over": "+3,5 buts",
    "BTTS||yes": "Les deux marquent",
    "TEAM_OU_HOME|0.5|over": "Domicile marque",
    "TEAM_OU_AWAY|0.5|over": "Extérieur marque",
    "TEAM_OU_HOME|1.5|over": "Domicile +1,5",
    "TEAM_OU_AWAY|1.5|over": "Extérieur +1,5",
    "HT_1X2||home": "Mi-temps : domicile",
    "HT_1X2||draw": "Mi-temps : nul",
    "HT_OU|0.5|over": "Mi-temps +0,5 but",
    "HT_OU|1.5|over": "Mi-temps +1,5 but",
}
HALF_TIME = ("HT_",)
NAIVE_SEASONS = 3
EPS = 1e-12
ALERT_SE = 3.0
MIN_CELL = 100

Row = tuple[str, int, float, float | None, int]  # championnat, saison, moteur, naïf, issue


def _settled_outcomes(hist: History, i: int) -> dict[str, int] | None:
    """Issue réelle (1 gagné / 0 perdu) de chaque groupe pour le match ``i``."""
    hg, ag = hist.hg[i], hist.ag[i]
    if np.isnan(hg) or np.isnan(ag) or max(hg, ag) > MAX_GOALS:
        return None
    has_ht = not (np.isnan(hist.hht[i]) or np.isnan(hist.aht[i]))
    hht, aht = (int(hist.hht[i]), int(hist.aht[i])) if has_ht else (0, 0)
    if max(hht, aht) > MAX_HT_GOALS:
        return None
    actual = derive_markets(actual_distribution(int(hg), int(ag), hht, aht))
    return {
        g: int(actual[g].win >= 0.999) for g in GOAL_GROUPS if has_ht or not g.startswith(HALF_TIME)
    }


def goal_rows(hist: History, pred: Predictions) -> dict[str, list[Row]]:
    """Lignes (championnat, saison, moteur, naïf, issue) par marché de buts."""
    # Référence naïve : issues des saisons précédentes, par championnat.
    seasons = sorted(set(pred.season))
    comps = sorted(set(pred.competition))
    first = min(seasons) - NAIVE_SEASONS
    history_rows = np.where(
        np.isin(hist.competition, comps)
        & (hist.season >= first)
        & (hist.season < max(seasons))
        & hist.finished
        & ~hist.excluded
    )[0]
    past: dict[tuple[str, int, str], list[int]] = defaultdict(list)
    for h in history_rows:
        outcomes = _settled_outcomes(hist, int(h))
        if outcomes is None:
            continue
        for g, o in outcomes.items():
            past[(str(hist.competition[h]), int(hist.season[h]), g)].append(o)

    def naive(comp: str, season: int, group: str) -> float | None:
        values = [
            o for s in range(season - NAIVE_SEASONS, season) for o in past.get((comp, s, group), [])
        ]
        # Lissage léger (une issue fictive de chaque côté) : jamais 0 ni 1.
        return (sum(values) + 1) / (len(values) + 2) if values else None

    out: dict[str, list[Row]] = defaultdict(list)
    for k in range(len(pred.row)):
        i = pred.row[k]
        outcomes = _settled_outcomes(hist, i)
        if outcomes is None:
            continue
        model = derive_markets(
            score_distribution(
                pred.lam_h[k], pred.lam_a[k], pred.rho[k], pred.share_h[k], pred.share_a[k]
            )
        )
        comp, season = pred.competition[k], pred.season[k]
        for g, o in outcomes.items():
            out[g].append((comp, season, model[g].win, naive(comp, season, g), o))
    return out


def _metrics(rows: Sequence[Row]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    p = np.clip(np.array([r[2] for r in rows]), EPS, 1 - EPS)
    y = np.array([r[4] for r in rows], dtype=np.float64)
    ll = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    out: dict[str, Any] = {
        "n": n,
        "announced": round(float(p.mean()), 4),
        "observed": round(float(y.mean()), 4),
        "gap": round(float(y.mean() - p.mean()), 4),
        "se": round(float(np.sqrt(np.sum(p * (1 - p))) / n), 4),
        "log_loss": round(ll, 4),
        "brier": round(float(np.mean((p - y) ** 2)), 4),
    }
    naive_rows = [r for r in rows if r[3] is not None]
    if len(naive_rows) == n:
        q = np.clip(np.array([r[3] for r in rows], dtype=np.float64), EPS, 1 - EPS)
        nll = float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))
        out["naive_log_loss"] = round(nll, 4)
        out["naive_brier"] = round(float(np.mean((q - y) ** 2)), 4)
        # Part de la log loss naïve gagnée par le moteur (positif = mieux).
        out["skill"] = round(1 - ll / nll, 4)
    return out


def _curve(rows: Sequence[Row], bins: int = 10) -> list[dict[str, Any]]:
    p = np.array([r[2] for r in rows])
    y = np.array([r[4] for r in rows], dtype=np.float64)
    out = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        mask = (p >= lo) & ((p < hi) if b < bins - 1 else (p <= hi))
        if mask.sum() == 0:
            continue
        pm = p[mask]
        out.append(
            {
                "from": lo,
                "to": hi,
                "n": int(mask.sum()),
                "announced": round(float(pm.mean()), 4),
                "observed": round(float(y[mask].mean()), 4),
                "se": round(float(np.sqrt(np.sum(pm * (1 - pm))) / mask.sum()), 4),
            }
        )
    return out


def calibration_report(groups: dict[str, list[Row]], labels: dict[str, str]) -> dict[str, Any]:
    report: dict[str, Any] = {"markets": {}, "alerts": []}
    cells = 0
    for g, rows in groups.items():
        by_comp: dict[str, list[Row]] = defaultdict(list)
        by_season: dict[int, list[Row]] = defaultdict(list)
        by_cell: dict[tuple[str, int], list[Row]] = defaultdict(list)
        for r in rows:
            by_comp[r[0]].append(r)
            by_season[r[1]].append(r)
            by_cell[(r[0], r[1])].append(r)
        report["markets"][g] = {
            "label": labels[g],
            "overall": _metrics(rows),
            "by_competition": {c: _metrics(v) for c, v in sorted(by_comp.items())},
            "by_season": {str(s): _metrics(v) for s, v in sorted(by_season.items())},
            "curve": _curve(rows),
        }
        for (comp, season), cell_rows in sorted(by_cell.items()):
            if len(cell_rows) < MIN_CELL:
                continue
            cells += 1
            m = _metrics(cell_rows)
            if abs(m["gap"]) > ALERT_SE * m["se"]:
                report["alerts"].append(
                    {"market": labels[g], "competition": comp, "season": season, **m}
                )
    report["cells_checked"] = cells
    return report


def counts_rows(rows: Iterable[tuple[str, int, float, float, int]]) -> list[Row]:
    return [(c, s, m, n, o) for c, s, m, n, o in rows]


def format_calibration(report: dict[str, Any]) -> str:
    def pct(x: float) -> str:
        return f"{x:+.1%}"

    lines = [
        "Calibration détaillée (hors échantillon)",
        "skill = part de la log loss naïve gagnée par le moteur (positif = mieux) ;",
        "écart = observé - annoncé (± 2 erreurs types).",
        "",
        f"{'Marché':<22}{'matchs':>7}{'log loss':>10}{'naïf':>8}{'skill':>8}{'Brier':>8}"
        f"{'annoncé':>9}{'observé':>9}   écart",
    ]
    for m in report["markets"].values():
        o = m["overall"]
        if not o.get("n"):
            continue
        naive = f"{o['naive_log_loss']:.4f}" if "naive_log_loss" in o else "—"
        skill = pct(o["skill"]) if "skill" in o else "—"
        lines.append(
            f"{m['label']:<22}{o['n']:>7}{o['log_loss']:>10.4f}{naive:>8}{skill:>8}"
            f"{o['brier']:>8.4f}{o['announced']:>9.1%}{o['observed']:>9.1%}"
            f"   {pct(o['gap'])} ±{2 * o['se']:.1%}"
        )
    comps = sorted({c for m in report["markets"].values() for c in m["by_competition"]})
    seasons = sorted({s for m in report["markets"].values() for s in m["by_season"]})
    for title, key, cols in (
        ("Écart par championnat", "by_competition", comps),
        ("Écart par saison", "by_season", seasons),
    ):
        lines += ["", title + " (observé - annoncé ; * au-delà de 2 erreurs types)"]
        lines.append(f"{'Marché':<22}" + "".join(f"{c[:10]:>12}" for c in cols))
        for m in report["markets"].values():
            cells = []
            for c in cols:
                v = m[key].get(c)
                if not v or not v.get("n"):
                    cells.append(f"{'—':>12}")
                    continue
                flag = "*" if abs(v["gap"]) > 2 * v["se"] else " "
                cells.append(f"{pct(v['gap']):>11}{flag}")
            lines.append(f"{m['label']:<22}" + "".join(cells))
    lines += [
        "",
        f"Alertes (écart > {ALERT_SE:g} erreurs types, cases d'au moins {MIN_CELL} matchs, "
        f"{report['cells_checked']} cases vérifiées) :",
    ]
    if not report["alerts"]:
        lines.append("  aucune")
    for a in report["alerts"]:
        lines.append(
            f"  {a['market']} — {a['competition']} {a['season']} : {a['n']} matchs, "
            f"annoncé {a['announced']:.1%}, observé {a['observed']:.1%} ({pct(a['gap'])})"
        )
    lines += [
        "",
        "Courbes de calibration détaillées (par tranche de 10 points) : fichier --output.",
    ]
    return "\n".join(lines)
