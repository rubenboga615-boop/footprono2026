"""Étude « angle du match » : choisir, pour chaque match, le marché le plus sûr.

Question du Coupon intelligent : si l'on prend, parmi les dizaines de marchés
d'un match, celui que le moteur juge le plus probable, la probabilité annoncée
reste-t-elle juste ? Prendre un maximum favorise les erreurs du modèle
(« malédiction du gagnant ») : il faut le mesurer avant de construire des
coupons dessus.

Méthode (strictement hors échantillon, sur les prédictions du backtest) :
- pour chaque match, tous les marchés « à deux issues » (gagné ou perdu,
  sans remboursement) sont tirés de la loi des scores du moteur, et réglés
  avec le vrai score (même fonction ``derive_markets`` appliquée à une loi
  qui met 100 % sur le score réel : règlement exactement cohérent) ;
- **calibration de référence** : toutes les sélections d'une tranche de
  probabilité, sans choix ;
- **angle du match** : dans chaque match, la sélection la plus probable de la
  tranche visée ; on compare l'annoncé à l'observé ;
- **coupons** : chaque jour, les K meilleurs angles de matchs différents,
  probabilité annoncée (produit) contre réussite réelle ;
- **cotes réelles** (1X2 et plus/moins 2,5 seulement : les seules cotes
  historiques) : rendement à mise fixe, sans rien cacher.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from footprono.engine.backtest import Predictions
from footprono.engine.history import History
from footprono.engine.markets import derive_markets
from footprono.engine.scores import (
    MAX_GOALS,
    MAX_HT_GOALS,
    ScoreDistribution,
    score_distribution,
)

# Marchés à deux issues (gagné / perdu) couramment proposés par les bookmakers.
CANDIDATE_MARKETS = frozenset(
    {
        "1X2", "DC", "OU", "TEAM_OU_HOME", "TEAM_OU_AWAY", "BTTS", "CLEAN_SHEET",
        "WIN_TO_NIL", "EH", "1X2_OU", "1X2_BTTS", "OU_BTTS",
        "HT_1X2", "HT_OU", "HT_BTTS", "HIGHEST_HALF",
    }
)  # fmt: skip
HALF_TIME_MARKETS = frozenset({"HT_1X2", "HT_OU", "HT_BTTS", "HIGHEST_HALF"})
# Familles lisibles pour le rapport.
FAMILY = {
    "1X2": "résultat", "DC": "double chance", "EH": "handicap européen",
    "OU": "buts du match", "TEAM_OU_HOME": "buts d'une équipe",
    "TEAM_OU_AWAY": "buts d'une équipe", "BTTS": "les deux marquent",
    "CLEAN_SHEET": "clean sheet", "WIN_TO_NIL": "clean sheet",
    "1X2_OU": "combiné du match", "1X2_BTTS": "combiné du match",
    "OU_BTTS": "combiné du match", "HT_1X2": "mi-temps", "HT_OU": "mi-temps",
    "HT_BTTS": "mi-temps", "HIGHEST_HALF": "mi-temps",
}  # fmt: skip
PROFILES = {"sûr": (0.75, 0.90), "équilibré": (0.60, 0.75), "audacieux": (0.45, 0.60)}
BANDS = [(0.45, 0.55), (0.55, 0.65), (0.65, 0.75), (0.75, 0.85), (0.85, 0.95)]
COUPON_SIZES = (2, 3, 4)


@dataclass(frozen=True)
class Pick:
    match_row: int
    day: np.datetime64
    key: str
    probability: float
    won: bool


def _market(key: str) -> str:
    return key.split("|", 1)[0]


def _actual(hg: int, ag: int, hht: int, aht: int) -> ScoreDistribution:
    joint = np.zeros((MAX_HT_GOALS + 1, MAX_HT_GOALS + 1, MAX_GOALS + 1, MAX_GOALS + 1))
    joint[hht, aht, hg, ag] = 1.0
    return ScoreDistribution(joint)


def match_selections(hist: History, pred: Predictions, k: int) -> list[tuple[str, float, bool]]:
    """(marché, probabilité du moteur, gagné) pour chaque sélection candidate d'un match."""
    i = pred.row[k]
    hg, ag = int(hist.hg[i]), int(hist.ag[i])
    has_ht = not (np.isnan(hist.hht[i]) or np.isnan(hist.aht[i]))
    hht, aht = (int(hist.hht[i]), int(hist.aht[i])) if has_ht else (0, 0)
    if max(hg, ag) > MAX_GOALS or max(hht, aht) > MAX_HT_GOALS:
        return []
    model = derive_markets(
        score_distribution(
            pred.lam_h[k], pred.lam_a[k], pred.rho[k], pred.share_h[k], pred.share_a[k]
        )
    )
    actual = derive_markets(_actual(hg, ag, hht, aht))
    out = []
    for key, sel in model.items():
        market = _market(key)
        if market not in CANDIDATE_MARKETS or (not has_ht and market in HALF_TIME_MARKETS):
            continue
        if sel.push or sel.half_win or sel.half_loss:
            continue
        out.append((key, sel.win, actual[key].win >= 0.999))
    return out


def _summary(p: Sequence[float], won: Sequence[bool]) -> dict[str, Any]:
    n = len(p)
    if n == 0:
        return {"n": 0}
    announced, observed = float(np.mean(p)), float(np.mean(won))
    # Erreur type de l'écart, sous l'hypothèse que l'annoncé est juste.
    se = float(np.sqrt(np.sum(np.asarray(p) * (1 - np.asarray(p)))) / n)
    return {
        "n": n,
        "announced": round(announced, 4),
        "observed": round(observed, 4),
        "gap": round(observed - announced, 4),
        "two_se": round(2 * se, 4),
    }


def _odds_profit(hist: History, pick: Pick) -> float | None:
    """Gain à mise 1 aux cotes de clôture réelles (1X2 et plus/moins 2,5), sinon None."""
    market, line, sel = pick.key.split("|")
    if market == "1X2":
        odds = hist.odds["close_1x2"][pick.match_row]
        price = odds[{"home": 0, "draw": 1, "away": 2}[sel]]
    elif market == "OU" and line == "2.5":
        odds = hist.odds["close_ou25"][pick.match_row]
        price = odds[0 if sel == "over" else 1]
    else:
        return None
    if np.isnan(price) or price <= 1:
        return None
    return float(price - 1) if pick.won else -1.0


def angles_study(hist: History, pred: Predictions) -> dict[str, Any]:
    all_p: dict[tuple[float, float], list[float]] = defaultdict(list)
    all_w: dict[tuple[float, float], list[bool]] = defaultdict(list)
    picks: dict[str, list[Pick]] = {name: [] for name in PROFILES}
    for k in range(len(pred.row)):
        sels = match_selections(hist, pred, k)
        for _key, p, won in sels:
            for band in BANDS:
                if band[0] <= p < band[1]:
                    all_p[band].append(p)
                    all_w[band].append(won)
        for name, (lo, hi) in PROFILES.items():
            inside = [s for s in sels if lo <= s[1] < hi]
            if inside:
                key, p, won = max(inside, key=lambda s: s[1])
                picks[name].append(Pick(pred.row[k], hist.date[pred.row[k]], key, p, won))

    report: dict[str, Any] = {
        "matches": len(pred.row),
        "reference": {
            f"{lo:.2f}-{hi:.2f}": _summary(all_p[(lo, hi)], all_w[(lo, hi)]) for lo, hi in BANDS
        },
        "profiles": {},
    }
    for name, chosen in picks.items():
        by_family: dict[str, list[Pick]] = defaultdict(list)
        for pk in chosen:
            by_family[FAMILY[_market(pk.key)]].append(pk)
        profits = [x for x in (_odds_profit(hist, pk) for pk in chosen) if x is not None]
        report["profiles"][name] = {
            "range": PROFILES[name],
            "angle": _summary([pk.probability for pk in chosen], [pk.won for pk in chosen]),
            "families": {
                fam: _summary([pk.probability for pk in fp], [pk.won for pk in fp])
                for fam, fp in sorted(by_family.items(), key=lambda kv: -len(kv[1]))
            },
            "coupons": _coupons(chosen),
            "real_odds": {
                "bets": len(profits),
                "roi": round(float(np.mean(profits)), 4) if profits else None,
                "two_se": round(float(2 * np.std(profits) / np.sqrt(len(profits))), 4)
                if len(profits) > 1
                else None,
            },
        }
    return report


def _coupons(chosen: Sequence[Pick]) -> dict[str, Any]:
    """Chaque jour, les K angles les plus probables (matchs différents) en un coupon."""
    by_day: dict[np.datetime64, list[Pick]] = defaultdict(list)
    for pk in chosen:
        by_day[pk.day].append(pk)
    out: dict[str, Any] = {}
    for size in COUPON_SIZES:
        announced, won = [], []
        for day_picks in by_day.values():
            if len(day_picks) < size:
                continue
            best = sorted(day_picks, key=lambda pk: -pk.probability)[:size]
            announced.append(float(np.prod([pk.probability for pk in best])))
            won.append(all(pk.won for pk in best))
        out[str(size)] = _summary(announced, won)
    return out


def format_report(report: dict[str, Any]) -> str:
    def row(label: str, s: dict[str, Any]) -> str:
        if not s.get("n"):
            return f"  {label:<26} —"
        return (
            f"  {label:<26} {s['n']:>7}  annoncé {s['announced']:.1%}  observé {s['observed']:.1%}"
            f"  écart {s['gap']:+.1%} (±{s['two_se']:.1%})"
        )

    lines = [f"Étude « angle du match » — {report['matches']} matchs (hors échantillon)", ""]
    lines.append("Référence : toutes les sélections, sans choix")
    lines += [row(band, s) for band, s in report["reference"].items()]
    for name, prof in report["profiles"].items():
        lo, hi = prof["range"]
        lines += [
            "",
            f"Profil « {name} » ({lo:.0%} à {hi:.0%}) : le marché le plus probable de chaque match",
        ]
        lines.append(row("angle choisi", prof["angle"]))
        lines.append("  par famille de marché :")
        lines += [row("  " + fam, s) for fam, s in prof["families"].items()]
        lines.append("  coupons du jour (angles les plus probables, matchs différents) :")
        lines += [row(f"  {size} sélections", s) for size, s in prof["coupons"].items()]
        odds = prof["real_odds"]
        if odds["bets"]:
            lines.append(
                f"  cotes réelles de clôture (1X2, +/-2,5 seulement) : {odds['bets']} paris, "
                f"rendement {odds['roi']:+.1%} (±{odds['two_se'] or 0:.1%})"
            )
    lines += [
        "",
        "Lecture : écart = observé - annoncé. Dans la marge ± (2 erreurs types), l'annonce est",
        "juste ; un écart négatif au-delà = le choix du « meilleur angle » surestime ses chances.",
    ]
    return "\n".join(lines)
