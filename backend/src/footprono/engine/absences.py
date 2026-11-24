"""Étude « compositions et absences » (testeur, 24/11/2026) : ``footprono-engine absences``.

Lancée depuis la console (Évaluer le moteur → Compositions et absences), sur les
compositions et fiches de joueurs gardées par « Compléter les matchs passés ».

Pour chaque équipe et chaque match, avec les seuls matchs d'avant (causalité stricte) :

- titulaires habituels : part des minutes de l'équipe jouées sur ses 10 derniers matchs de
  championnat ; « absent » = habituel (≥ 60 %) qui n'est pas titulaire ce jour-là ;
- ``manque`` : somme des parts des habituels absents, divisée par 11 (0 = équipe type,
  0,2 ≈ deux titulaires habituels absents) ;
- ``manque_attaque`` : part des buts + passes décisives de l'équipe (10 derniers matchs)
  apportée par les absents ;
- ``manque_defense`` : gardien et défenseurs habituels absents (part, divisée par 5) ;
- ``nouvel_entraineur`` : entraîneur différent de celui du match précédent, dans les 5
  premiers matchs.

Puis les buts attendus du moteur (λ, prévisions hors échantillon) sont corrigés :
λ' = λ · exp(b · indicateurs de l'équipe + g · indicateurs de l'adversaire), b et g appris
sur 2019-20 → 2021-22, mesurés sur 2022-23 → 2025-26 : log loss 1X2 et plus/moins 2,5,
contre le moteur seul et contre la cote de clôture (Pinnacle, marge retirée).
"""

from collections import defaultdict, deque
from typing import Any

import numpy as np
from scipy.optimize import minimize
from sqlalchemy import text

from footprono.core.config import get_settings
from footprono.db.session import create_engine, create_session_factory
from footprono.engine.backtest import Predictions, match_probabilities
from footprono.engine.history import History

WINDOW = 10
REGULAR = 0.6
FEATURES = ("manque", "manque_attaque", "manque_defense", "nouvel_entraineur")
EPS = 1e-12

_ROWS = text(
    """
    SELECT m.id, m.kickoff_at, m.match_date, lp.side, lp.player_api_id, lp.starter, lp.position,
           ps.minutes, ps.goals, ps.assists, l.coach_api_id,
           CASE WHEN lp.side = 'home' THEN m.home_team_id ELSE m.away_team_id END AS team
    FROM match_lineup_players lp
    JOIN matches m ON m.id = lp.match_id
    JOIN seasons s ON s.id = m.season_id
    JOIN competitions c ON c.id = s.competition_id
    LEFT JOIN player_match_stats ps
      ON ps.match_id = lp.match_id AND ps.player_api_id = lp.player_api_id
    LEFT JOIN match_lineups l ON l.match_id = lp.match_id AND l.side = lp.side
    WHERE c.code = ANY(:codes) AND lp.player_api_id IS NOT NULL
    ORDER BY m.match_date, m.kickoff_at NULLS LAST, m.id
    """
)


async def load_rows(codes: list[str]) -> list[Any]:
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            return list((await session.execute(_ROWS, {"codes": codes})).all())
    finally:
        await engine.dispose()


def features(rows: list[Any]) -> dict[tuple[int, str], dict[str, float]]:
    """{(match, side): indicateurs}, calculés avant le match avec les seuls matchs d'avant."""
    by_match: dict[tuple[int, str], list[Any]] = defaultdict(list)
    order: list[tuple[int, str]] = []
    for r in rows:
        k = (r.id, r.side)
        if k not in by_match:
            order.append(k)
        by_match[k].append(r)
    history: dict[int, deque[dict[int, tuple[float, float, str | None]]]] = defaultdict(
        lambda: deque(maxlen=WINDOW)
    )
    coach: dict[int, tuple[int | None, int]] = {}
    out: dict[tuple[int, str], dict[str, float]] = {}
    for k in order:
        players = by_match[k]
        team = players[0].team
        past = history[team]
        starters = {p.player_api_id for p in players if p.starter}
        if len(past) >= 5 and len(starters) >= 10:
            minutes: dict[int, float] = defaultdict(float)
            contrib: dict[int, float] = defaultdict(float)
            position: dict[int, str | None] = {}
            for game in past:
                for pid, (mins, ga, pos) in game.items():
                    minutes[pid] += mins
                    contrib[pid] += ga
                    position[pid] = pos or position.get(pid)
            share = {pid: m / (90 * len(past)) for pid, m in minutes.items()}
            regular = {pid for pid, s in share.items() if s >= REGULAR}
            absent = regular - starters
            total_ga = sum(contrib.values())
            defenders = {pid for pid in regular if position.get(pid) in ("G", "D")}
            since = coach.get(team, (None, 99))[1]
            out[k] = {
                "manque": sum(share[p] for p in absent) / 11,
                "manque_attaque": (sum(contrib[p] for p in absent) / total_ga) if total_ga else 0,
                "manque_defense": sum(share[p] for p in absent & defenders) / 5,
                "nouvel_entraineur": float(since < 5),
            }
        game = {
            p.player_api_id: (
                float(p.minutes or 0),
                float((p.goals or 0) + (p.assists or 0)),
                p.position,
            )
            for p in players
        }
        past.append(game)
        c = players[0].coach_api_id
        prev, since = coach.get(team, (None, 99))
        coach[team] = (c, 0 if (prev is not None and c is not None and c != prev) else since + 1)
    return out


def _probs(lh: float, la: float, rho: float, sh: float, sa: float) -> tuple[np.ndarray, float]:
    mp = match_probabilities(lh, la, rho, sh, sa)
    return mp.p1x2, mp.ou25


def _losses(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.asarray(-np.log(np.clip(p[np.arange(len(y)), y], EPS, 1)), dtype=np.float64)


def _se(d: np.ndarray) -> str:
    return f"{d.mean():+.4f} ± {2 * d.std(ddof=1) / np.sqrt(len(d)):.4f}"


def report(
    hist: History,
    pred: Predictions,
    rows: list[Any],
    validation: list[int],
    test_seasons: list[int],
) -> None:
    """Imprime l'étude ; ``pred`` : prévisions hors échantillon sur validation + test."""
    VALIDATION, TEST = tuple(validation), tuple(test_seasons)
    feats = features(rows)
    print(f"{len(rows)} lignes de composition, indicateurs pour {len(feats)} équipes-matchs\n")
    keep = [
        i for i, mid in enumerate(pred.match_id)
        if (mid, "home") in feats and (mid, "away") in feats
    ]  # fmt: skip
    print(f"{len(keep)} matchs prédits avec les deux compositions\n")
    if len(keep) < 500:
        print("Trop peu de matchs : relancer « Compléter les matchs passés ».")
        return
    mid = np.array(pred.match_id)[keep]
    season = np.array(pred.season)[keep]
    lam_h, lam_a = np.array(pred.lam_h)[keep], np.array(pred.lam_a)[keep]
    rho = np.array(pred.rho)[keep]
    sh, sa = np.array(pred.share_h)[keep], np.array(pred.share_a)[keep]
    y1 = np.array(pred.outcome_1x2)[keep]
    yo = np.array(pred.outcome_ou25)[keep]
    close = np.array(pred.market_close_1x2)[keep]
    fh = np.array([[feats[(m, "home")][f] for f in FEATURES] for m in mid])
    fa = np.array([[feats[(m, "away")][f] for f in FEATURES] for m in mid])
    rows_idx = np.array(pred.row)[keep]
    hg, ag = hist.hg[rows_idx], hist.ag[rows_idx]

    print("## Indicateurs (moyenne, part des matchs non nuls)\n")
    for j, f in enumerate(FEATURES):
        v = np.concatenate([fh[:, j], fa[:, j]])
        print(f"- {f} : moyenne {v.mean():.3f}, non nul {np.mean(v > 0):.0%}")

    # Poisson sur les buts : log λ' = log λ + b·(indicateurs de l'équipe) + g·(adversaire).
    def nll(theta: np.ndarray, m: np.ndarray) -> float:
        b, g = theta[: len(FEATURES)], theta[len(FEATURES) :]
        lh = lam_h[m] * np.exp(fh[m] @ b + fa[m] @ g)
        la = lam_a[m] * np.exp(fa[m] @ b + fh[m] @ g)
        return float(np.sum(lh - hg[m] * np.log(lh)) + np.sum(la - ag[m] * np.log(la)))

    val, test = np.isin(season, VALIDATION), np.isin(season, TEST)
    theta = minimize(nll, np.zeros(2 * len(FEATURES)), args=(val,), method="BFGS").x
    print(
        f"\n## Réglages appris sur {VALIDATION[0]}-{VALIDATION[-1] + 1} "
        "(effet sur les buts attendus)\n"
    )
    for j, f in enumerate(FEATURES):
        print(
            f"- {f} : sur les buts de l'équipe x {np.exp(theta[j] * 0.1):.3f} pour +0,1 ; "
            f"sur ceux de l'adversaire x {np.exp(theta[len(FEATURES) + j] * 0.1):.3f}"
        )
    b, g = theta[: len(FEATURES)], theta[len(FEATURES) :]
    idx = np.where(test)[0]
    base1, adj1, baseo, adjo = [], [], [], []
    for i in idx:
        p, o = _probs(lam_h[i], lam_a[i], rho[i], sh[i], sa[i])
        lh = lam_h[i] * np.exp(fh[i] @ b + fa[i] @ g)
        la = lam_a[i] * np.exp(fa[i] @ b + fh[i] @ g)
        q, oq = _probs(lh, la, rho[i], sh[i], sa[i])
        base1.append(p)
        adj1.append(q)
        baseo.append([o, 1 - o])
        adjo.append([oq, 1 - oq])
    y1t = y1[idx].astype(int)
    yot = np.where(yo[idx] == 1, 0, 1)
    l_base = _losses(np.array(base1), y1t)
    l_adj = _losses(np.array(adj1), y1t)
    o_base = _losses(np.array(baseo), yot)
    o_adj = _losses(np.array(adjo), yot)
    print(f"\n## Saisons de test ({len(idx)} matchs)\n")
    print("| Marché | Moteur | Moteur + compositions | Écart |")
    print("|---|---|---|---|")
    print(f"| 1X2 | {l_base.mean():.4f} | {l_adj.mean():.4f} | {_se(l_adj - l_base)} |")
    print(f"| +/-2,5 | {o_base.mean():.4f} | {o_adj.mean():.4f} | {_se(o_adj - o_base)} |")
    # Probabilités de la clôture, marge déjà retirée (backtest._implied).
    ok = np.all(np.isfinite(close[idx]), axis=1)
    if ok.sum() > 100:
        pm = close[idx][ok]
        l_m = _losses(pm, y1t[ok])
        print(
            f"\nCote de clôture sur les mêmes {ok.sum()} matchs : {l_m.mean():.4f} "
            f"(moteur {l_base[ok].mean():.4f}, avec compositions {l_adj[ok].mean():.4f}) ; "
            f"écart moteur - clôture {_se(l_base[ok] - l_m)}, "
            f"avec compositions - clôture {_se(l_adj[ok] - l_m)}"
        )
    big = np.maximum(fh[idx, 0], fa[idx, 0]) >= 0.15
    if big.sum() > 50:
        print(
            f"\nMatchs avec au moins ~2 titulaires habituels absents d'un côté ({big.sum()}) : "
            f"1X2 {_se(l_adj[big] - l_base[big])}"
        )
