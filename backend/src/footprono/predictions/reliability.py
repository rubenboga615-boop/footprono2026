"""Fiabilité publique : ce que le moteur a annoncé avant les matchs, face aux résultats.

Règles (docs/PRODUIT.md) :

- Seules comptent les prédictions **enregistrées avant le coup d'envoi**
  (``created_at`` < heure du match ; sans heure connue, minuit UTC du jour du
  match). Pour chaque match, la dernière d'entre elles. Rien n'est recalculé
  après coup.
- Toutes les prédictions retenues comptent, bonnes ou mauvaises : aucun tri.
- Références affichées à côté : fréquences observées sur le même échantillon
  (référence naïve) et cotes de clôture des bookmakers quand elles existent
  (elles restent en général meilleures que le moteur : c'est dit, pas caché).
- Les chiffres du backtest (simulation sur des saisons passées) sont donnés à
  part et présentés comme tels.
- Sous ``MIN_SAMPLE`` matchs, l'échantillon est signalé trop petit pour conclure.
"""

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.engine.history import MARKET_BOOKMAKERS
from footprono.engine.tiers import tier

MIN_SAMPLE = 200
EPS = 1e-12
BINS = 10

# Probabilités lues dans chaque prédiction : marché -> clés des issues.
MARKETS: dict[str, tuple[str, ...]] = {
    "1X2": ("1X2||home", "1X2||draw", "1X2||away"),
    "OU|2.5": ("OU|2.5|over", "OU|2.5|under"),
    "BTTS": ("BTTS||yes", "BTTS||no"),
}
LABELS = {
    "1X2": "Résultat du match (1X2)",
    "OU|2.5": "Plus/moins de 2,5 buts",
    "BTTS": "Les deux équipes marquent",
}
OUTCOMES = {
    "1X2": ("domicile", "nul", "extérieur"),
    "OU|2.5": ("plus de 2,5", "moins de 2,5"),
    "BTTS": ("oui", "non"),
}

# Backtest du 30/09/2026 (docs/MOTEUR.md) : saisons 2022-23 à 2025-26,
# 7 081 matchs jamais vus pendant le réglage, chaque match prédit avec les
# seuls matchs joués avant lui. Log loss : plus bas = meilleur.
BACKTEST: dict[str, Any] = {
    "label": "Backtest des 5 grands championnats : simulation sur des saisons passées",
    "verified_on": "2026-09-30",
    "seasons": "2022-23 à 2025-26",
    "matches": 7081,
    "engine_version": "2.1",
    "log_loss": {
        "1X2": {"model": 0.9827, "naive": 1.0731, "closing_odds": 0.9665},
        "OU|2.5": {"model": 0.6768, "naive": 0.6873, "closing_odds": 0.6677},
        "BTTS": {"model": 0.6844, "naive": 0.6884, "closing_odds": None},
    },
    "calibration_1x2": [
        {"range": "0,0-0,1", "count": 549, "announced": 0.074, "observed": 0.060},
        {"range": "0,1-0,2", "count": 3040, "announced": 0.160, "observed": 0.153},
        {"range": "0,2-0,3", "count": 8366, "announced": 0.250, "observed": 0.256},
        {"range": "0,3-0,4", "count": 3164, "announced": 0.346, "observed": 0.335},
        {"range": "0,4-0,5", "count": 2498, "announced": 0.448, "observed": 0.447},
        {"range": "0,5-0,6", "count": 1832, "announced": 0.547, "observed": 0.550},
        {"range": "0,6-0,7", "count": 1076, "announced": 0.647, "observed": 0.648},
        {"range": "0,7-0,8", "count": 538, "announced": 0.742, "observed": 0.764},
        {"range": "0,8-0,9", "count": 168, "announced": 0.840, "observed": 0.851},
    ],
    "note": (
        "Le moteur bat nettement la référence naïve mais reste derrière les cotes de "
        "clôture des bookmakers : il n'annonce pas de « bons coups » contre eux."
    ),
}

# Championnats de niveau 2 (sans xG : tirs de football-data, ou d'API-Football pour la
# Suisse, la Norvège, la Suède, le Danemark et l'Autriche ; engine/tiers.py). Backtest du
# 04/10/2026 sur les données chargées par le serveur (secondes phases comprises), écart
# favori / outsider appris par championnat, chaque saison sur les saisons précédentes.
# Pas de cotes de clôture passées pour les championnats d'API-Football : la comparaison
# au marché porte sur les 6891 matchs qui en ont (note).
BACKTEST_LEVEL_2: dict[str, Any] = {
    "label": "Backtest des onze championnats sans xG : simulation sur des saisons passées",
    "verified_on": "2026-10-04",
    "seasons": "2022-23 à 2025-26",
    "matches": 11210,
    "engine_version": "2.3",
    "log_loss": {
        "1X2": {"model": 0.9795, "naive": 1.0714, "closing_odds": None},
        "OU|2.5": {"model": 0.6782, "naive": 0.6873, "closing_odds": None},
    },
    "calibration_1x2": [
        {"range": "0,0-0,1", "count": 1509, "announced": 0.065, "observed": 0.072},
        {"range": "0,1-0,2", "count": 4369, "announced": 0.158, "observed": 0.160},
        {"range": "0,2-0,3", "count": 13109, "announced": 0.252, "observed": 0.260},
        {"range": "0,3-0,4", "count": 5042, "announced": 0.347, "observed": 0.340},
        {"range": "0,4-0,5", "count": 4004, "announced": 0.448, "observed": 0.427},
        {"range": "0,5-0,6", "count": 2588, "announced": 0.546, "observed": 0.555},
        {"range": "0,6-0,7", "count": 1476, "announced": 0.645, "observed": 0.631},
        {"range": "0,7-0,8", "count": 934, "announced": 0.746, "observed": 0.757},
        {"range": "0,8-0,9", "count": 518, "announced": 0.843, "observed": 0.830},
        {"range": "0,9-1,0", "count": 81, "announced": 0.921, "observed": 0.877},
    ],
    "note": (
        "Moins de données que dans les 5 grands championnats (pas de xG) : pourcentages un "
        "peu moins précis, et pas d'avis du moteur sur « les deux marquent » (pas mieux que "
        "la fréquence du championnat). Face aux cotes de clôture, sur les 6 891 matchs "
        "qui en ont (pas d'historique de cotes pour la Suisse, la Norvège, la Suède, le "
        "Danemark et l'Autriche) : 1-N-2 0,9567 pour le moteur contre "
        "0,9382 pour la clôture ; plus/moins 2,5 0,6769 contre "
        "0,6685. Le moteur reste derrière les cotes de clôture."
    ),
}


def backtest_for(competition: str | None) -> dict[str, Any]:
    """Backtest à montrer pour un filtre de championnat (niveau de données)."""
    if competition is not None and tier(competition.upper()).level == 2:
        return BACKTEST_LEVEL_2
    return BACKTEST


_PREDICTIONS = text(
    """
    SELECT DISTINCT ON (mp.match_id)
        mp.match_id, m.match_date, c.code, th.name, ta.name, m.home_goals, m.away_goals,
        mp.created_at, r.engine_version,
        (mp.markets->'1X2||home'->>0)::float, (mp.markets->'1X2||draw'->>0)::float,
        (mp.markets->'1X2||away'->>0)::float, (mp.markets->'OU|2.5|over'->>0)::float,
        (mp.markets->'BTTS||yes'->>0)::float
    FROM match_predictions mp
    JOIN prediction_runs r ON r.id = mp.run_id
    JOIN matches m ON m.id = mp.match_id
    JOIN seasons s ON s.id = m.season_id
    JOIN competitions c ON c.id = s.competition_id
    JOIN teams th ON th.id = m.home_team_id
    JOIN teams ta ON ta.id = m.away_team_id
    WHERE m.status = 'finished'
      AND m.home_goals IS NOT NULL AND m.away_goals IS NOT NULL
      AND mp.created_at < COALESCE(m.kickoff_at, m.match_date::timestamp AT TIME ZONE 'UTC')
      AND (CAST(:competition AS text) IS NULL OR c.code = :competition)
      AND (CAST(:since AS date) IS NULL OR m.match_date >= :since)
    ORDER BY mp.match_id, mp.created_at DESC
    """
)

_CLOSING = text(
    """
    SELECT match_id, bookmaker, market, selection, price
    FROM match_odds
    WHERE match_id = ANY(:ids) AND timing = 'close' AND bookmaker = ANY(:books)
      AND (market = '1X2' OR (market = 'OU' AND line = 2.5))
    """
)
_CLOSING_SLOTS = {
    ("1X2", "home"): ("1X2", 0), ("1X2", "draw"): ("1X2", 1), ("1X2", "away"): ("1X2", 2),
    ("OU", "over"): ("OU|2.5", 0), ("OU", "under"): ("OU|2.5", 1),
}  # fmt: skip


@dataclass(frozen=True)
class Scored:
    """Une prédiction retenue : probabilités annoncées et issue réelle par marché."""

    match_id: int
    match_date: date
    competition: str
    home: str
    away: str
    score: tuple[int, int]
    engine_version: str
    probs: dict[str, tuple[float, ...]]
    outcome: dict[str, int]


def _outcomes(hg: int, ag: int) -> dict[str, int]:
    return {
        "1X2": 0 if hg > ag else (1 if hg == ag else 2),
        "OU|2.5": 0 if hg + ag > 2 else 1,
        "BTTS": 0 if hg > 0 and ag > 0 else 1,
    }


def _log_loss(p: float) -> float:
    return -math.log(max(p, EPS))


def _market_summary(rows: list[Scored], market: str) -> dict[str, Any]:
    rows = [r for r in rows if market in r.probs]
    n = len(rows)
    size = len(MARKETS[market])
    if n == 0:
        return {"market": market, "label": LABELS[market], "matches": 0}
    counts = [0] * size
    ll = brier = hits = pick_prob = 0.0
    for r in rows:
        p, o = r.probs[market], r.outcome[market]
        counts[o] += 1
        ll += _log_loss(p[o])
        brier += sum((p[k] - (k == o)) ** 2 for k in range(size))
        pick = max(range(size), key=lambda k: p[k])
        hits += pick == o
        pick_prob += p[pick]
    freq = [c / n for c in counts]
    naive = sum(_log_loss(freq[r.outcome[market]]) for r in rows) / n
    return {
        "market": market,
        "label": LABELS[market],
        "matches": n,
        "log_loss": round(ll / n, 4),
        "naive_log_loss": round(naive, 4),
        "brier": round(brier / n, 4),
        # Issue la plus probable selon le moteur : trouvée combien de fois, et
        # combien de fois le moteur l'annonçait en moyenne (les deux doivent se
        # rapprocher si les probabilités sont justes).
        "most_likely_hit_rate": round(hits / n, 4),
        "most_likely_announced": round(pick_prob / n, 4),
        "observed_frequencies": dict(
            zip(OUTCOMES[market], [round(f, 4) for f in freq], strict=True)
        ),
        "calibration": _calibration(rows, market),
    }


def _calibration(rows: list[Scored], market: str) -> list[dict[str, Any]]:
    """Probabilité annoncée (par tranche de 10 %) → fréquence observée, toutes issues."""
    bins: dict[int, list[float]] = defaultdict(lambda: [0, 0.0, 0.0])
    for r in rows:
        if market not in r.probs:
            continue
        for k, p in enumerate(r.probs[market]):
            b = bins[min(int(p * BINS), BINS - 1)]
            b[0] += 1
            b[1] += p
            b[2] += r.outcome[market] == k
    return [
        {
            "range": f"{i / BINS:.1f}-{(i + 1) / BINS:.1f}".replace(".", ","),
            "count": int(b[0]),
            "announced": round(b[1] / b[0], 4),
            "observed": round(b[2] / b[0], 4),
        }
        for i, b in sorted(bins.items())
    ]


async def _closing_probs(
    session: AsyncSession, ids: list[int]
) -> dict[tuple[int, str], tuple[float, ...]]:
    """Probabilités des cotes de clôture (marge retirée), un seul bookmaker par marché."""
    quotes: dict[tuple[int, str], dict[str, dict[int, float]]] = {}
    for mid, book, market, selection, price in (
        await session.execute(_CLOSING, {"ids": ids, "books": list(MARKET_BOOKMAKERS)})
    ).all():
        slot = _CLOSING_SLOTS.get((market, selection))
        if slot is not None:
            quotes.setdefault((mid, slot[0]), {}).setdefault(book, {})[slot[1]] = float(price)
    out = {}
    for (mid, market), books in quotes.items():
        size = len(MARKETS[market])
        for book in MARKET_BOOKMAKERS:
            prices = books.get(book, {})
            if len(prices) == size and all(v > 1 for v in prices.values()):
                inv = [1 / prices[k] for k in range(size)]
                out[(mid, market)] = tuple(x / sum(inv) for x in inv)
                break
    return out


def _versus_closing(
    rows: list[Scored], market: str, closing: dict[tuple[int, str], tuple[float, ...]]
) -> dict[str, Any] | None:
    both = [
        (r, closing[(r.match_id, market)])
        for r in rows
        if market in r.probs and (r.match_id, market) in closing
    ]
    if not both:
        return None
    n = len(both)
    return {
        "market": market,
        "matches": n,
        "model_log_loss": round(
            sum(_log_loss(r.probs[market][r.outcome[market]]) for r, _ in both) / n, 4
        ),
        "closing_odds_log_loss": round(
            sum(_log_loss(c[r.outcome[market]]) for r, c in both) / n, 4
        ),
    }


async def load_scored(
    session: AsyncSession, *, competition: str | None = None, since: date | None = None
) -> list[Scored]:
    rows = (await session.execute(_PREDICTIONS, {"competition": competition, "since": since})).all()
    out = []
    for mid, day, comp, home, away, hg, ag, _created, version, ph, pd, pa, over, yes in rows:
        if None in (ph, pd, pa, over):
            continue
        probs = {"1X2": (ph, pd, pa), "OU|2.5": (over, 1 - over)}
        if yes is not None:  # absent au niveau de données 2 (engine/tiers.py)
            probs["BTTS"] = (yes, 1 - yes)
        out.append(
            Scored(
                match_id=mid, match_date=day, competition=comp, home=home, away=away,
                score=(hg, ag), engine_version=version, probs=probs, outcome=_outcomes(hg, ag),
            )
        )  # fmt: skip
    out.sort(key=lambda r: (r.match_date, r.match_id))
    return out


async def reliability_report(
    session: AsyncSession,
    *,
    competition: str | None = None,
    since: date | None = None,
    recent: int = 20,
) -> dict[str, Any]:
    rows = await load_scored(session, competition=competition, since=since)
    n = len(rows)
    closing = await _closing_probs(session, [r.match_id for r in rows]) if rows else {}
    by_comp: dict[str, list[Scored]] = defaultdict(list)
    for r in rows:
        by_comp[r.competition].append(r)
    if n == 0:
        warning = "Aucune prédiction publiée avant un match terminé pour l'instant."
    elif n < MIN_SAMPLE:
        warning = (
            f"Seulement {n} matchs : échantillon trop petit pour conclure "
            f"(il en faut au moins {MIN_SAMPLE}). Voir aussi le backtest."
        )
    else:
        warning = None
    return {
        "rule": (
            "Prédictions enregistrées avant le coup d'envoi, jamais modifiées, "
            "toutes comptées face aux résultats réels."
        ),
        "references": {
            "log_loss": (
                "plus bas = meilleur ; sans aucune information : 1,0986 en 1X2, 0,6931 sinon"
            ),
            "naive": (
                "fréquences observées sur ce même échantillon, connues seulement après coup "
                "(référence avantagée)"
            ),
            "closing_odds": (
                "cotes de clôture des bookmakers, marge retirée : elles intègrent tout ce qui "
                "est connu jusqu'au coup d'envoi"
            ),
        },
        "filters": {"competition": competition, "since": since},
        "matches": n,
        "period": {"from": rows[0].match_date, "to": rows[-1].match_date} if rows else None,
        "engine_versions": sorted({r.engine_version for r in rows}),
        "enough_data": n >= MIN_SAMPLE,
        "warning": warning,
        "markets": [_market_summary(rows, m) for m in MARKETS],
        "versus_closing_odds": [
            v for m in ("1X2", "OU|2.5") if (v := _versus_closing(rows, m, closing)) is not None
        ],
        "by_competition": [
            {
                "competition": comp,
                "matches": len(items),
                "log_loss_1x2": _market_summary(items, "1X2")["log_loss"],
                "naive_log_loss_1x2": _market_summary(items, "1X2")["naive_log_loss"],
            }
            for comp, items in sorted(by_comp.items())
        ],
        "recent": [
            {
                "match_id": r.match_id,
                "date": r.match_date,
                "competition": r.competition,
                "home": r.home,
                "away": r.away,
                "score": f"{r.score[0]}-{r.score[1]}",
                "probabilities_1x2": [round(p, 4) for p in r.probs["1X2"]],
                "most_likely": OUTCOMES["1X2"][max(range(3), key=lambda k: r.probs["1X2"][k])],
                "result": OUTCOMES["1X2"][r.outcome["1X2"]],
            }
            for r in reversed(rows[-recent:] if recent else [])
        ],
        "backtest": backtest_for(competition),
    }
