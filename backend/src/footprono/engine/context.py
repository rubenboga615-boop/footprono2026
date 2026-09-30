"""Contexte de chaque match, calculé uniquement avec ce qui était connu avant lui.

Tout est **dérivé** des résultats déjà en base (aucune source supplémentaire,
aucune valeur inventée) :

- classement avant le match (points, différence de buts, buts marqués), mis à
  jour seulement avec les matchs des jours précédents ;
- avancement de la saison (part des matchs du championnat déjà joués), qui
  rend comparables les championnats à 18 et à 20 équipes ;
- enjeu : écart avec les lignes de classement qui comptent (titre, 4e, 6e,
  maintien) et match « sans enjeu » quand l'équipe ne peut plus franchir
  aucune de ces lignes, ni vers le haut ni vers le bas ;
- repos : jours depuis le dernier match de championnat (les coupes ne sont
  pas en base : le repos réel peut être plus court) ;
- dynamique : moyenne des 5 derniers matchs moins moyenne des 20 derniers
  (différence de xG, ou de buts quand le xG manque) ;
- réussite de la saison : buts moins xG par match (tend à revenir à zéro).

Limites connues : les pénalités de points infligées par les ligues ne sont
pas en base ; les lignes européennes réelles varient selon les années et les
coupes nationales (on retient les 4e et 6e places).
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from footprono.engine.history import History

FloatArray = NDArray[np.float64]

FORM_SHORT = 5
FORM_LONG = 20
REST_CAP_DAYS = 14
FIGHT_POINTS = 6  # « à la lutte » : à 6 points ou moins d'une ligne
FIGHT_FROM = 0.6  # … à partir de 60 % de la saison
TEAM_FEATURES = ("rest", "dead", "fight_top", "fight_bottom", "form", "luck")


@dataclass
class MatchContext:
    """Une ligne par match de l'historique ; ``team[nom]`` = (domicile, extérieur)."""

    progress: FloatArray
    team: dict[str, tuple[FloatArray, FloatArray]] = field(default_factory=dict)
    rank: tuple[FloatArray, FloatArray] | None = None
    points: tuple[FloatArray, FloatArray] | None = None


def _boundaries(n_teams: int) -> tuple[int, ...]:
    # Ligne entre la place b et la place b + 1 : titre, 4e, 6e, dernier maintenu.
    # 20 équipes : relégués 18-20 ; 18 équipes : barragiste 16e puis 17-18.
    return (1, 4, 6, n_teams - 3)


@dataclass
class _Table:
    points: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    played: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    gd: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    gf: dict[int, int] = field(default_factory=lambda: defaultdict(int))

    def order(self, teams: list[int]) -> list[int]:
        return sorted(teams, key=lambda t: (-self.points[t], -self.gd[t], -self.gf[t], t))


def _enjeu(
    table: _Table, teams: list[int], rounds: int, progress: float
) -> dict[int, tuple[float, float, float]]:
    """Par équipe : (sans enjeu, lutte en haut, lutte en bas)."""
    order = table.order(teams)
    pos = {t: k + 1 for k, t in enumerate(order)}
    out = {}
    for t in teams:
        pts, left = table.points[t], rounds - table.played[t]
        settled = True
        near: dict[int, bool] = {}
        for b in _boundaries(len(teams)):
            if pos[t] <= b:  # au-dessus de la ligne : peut-on encore la repasser ?
                other = order[b]
                gap = pts - table.points[other]
                can_move = pts <= table.points[other] + 3 * (rounds - table.played[other])
            else:
                other = order[b - 1]
                gap = table.points[other] - pts
                can_move = pts + 3 * left >= table.points[other]
            settled &= not can_move
            near[b] = progress >= FIGHT_FROM and gap <= FIGHT_POINTS and can_move
        bounds = _boundaries(len(teams))
        out[t] = (
            float(settled),
            float(near[bounds[0]] or near[bounds[1]]),
            float(near[bounds[3]]),
        )
    return out


def build_context(hist: History) -> MatchContext:
    n = len(hist)
    progress = np.zeros(n)
    feats = {name: (np.zeros(n), np.zeros(n)) for name in TEAM_FEATURES}
    rank = (np.zeros(n), np.zeros(n))
    points = (np.zeros(n), np.zeros(n))

    last_day: dict[tuple[str, int], np.datetime64] = {}
    diffs: dict[tuple[str, int], deque[float]] = defaultdict(lambda: deque(maxlen=FORM_LONG))

    for comp in np.unique(hist.competition):
        for season in np.unique(hist.season[hist.competition == comp]):
            rows = np.where((hist.competition == comp) & (hist.season == season))[0]
            rows = rows[np.argsort(hist.date[rows], kind="stable")]
            teams = sorted({int(t) for t in np.concatenate([hist.home[rows], hist.away[rows]])})
            rounds = 2 * (len(teams) - 1)
            total = len(teams) * (len(teams) - 1)
            table = _Table()
            luck: dict[int, list[float]] = defaultdict(list)
            played_matches = 0
            for day in np.unique(hist.date[rows]):
                today = rows[hist.date[rows] == day]
                share = played_matches / total
                stakes = _enjeu(table, teams, rounds, share)
                order = table.order(teams)
                pos = {t: k + 1 for k, t in enumerate(order)}
                for i in today:
                    progress[i] = share
                    for side, team in enumerate((int(hist.home[i]), int(hist.away[i]))):
                        key = (str(comp), team)
                        prev = last_day.get(key)
                        days = REST_CAP_DAYS if prev is None else int((day - prev).astype(int))
                        feats["rest"][side][i] = (min(days, REST_CAP_DAYS) - 7) / 7
                        dead, top, bottom = stakes[team]
                        feats["dead"][side][i] = dead
                        feats["fight_top"][side][i] = top
                        feats["fight_bottom"][side][i] = bottom
                        past = diffs[key]
                        if len(past) >= 2 * FORM_SHORT:
                            recent = list(past)[-FORM_SHORT:]
                            feats["form"][side][i] = float(np.mean(recent) - np.mean(past))
                        if len(luck[team]) >= FORM_SHORT:
                            feats["luck"][side][i] = float(np.mean(luck[team]))
                        rank[side][i] = pos[team]
                        points[side][i] = table.points[team]
                # Mise à jour après la journée : seuls les matchs terminés comptent.
                for i in today:
                    if not hist.finished[i] or np.isnan(hist.hg[i]):
                        continue
                    h, a = int(hist.home[i]), int(hist.away[i])
                    hg, ag = int(hist.hg[i]), int(hist.ag[i])
                    played_matches += 1
                    for team, gf, ga in ((h, hg, ag), (a, ag, hg)):
                        table.played[team] += 1
                        table.gf[team] += gf
                        table.gd[team] += gf - ga
                        table.points[team] += 3 if gf > ga else (1 if gf == ga else 0)
                    xgs = (hist.hxg[i], hist.axg[i])
                    has_xg = not (np.isnan(xgs[0]) or np.isnan(xgs[1]))
                    for team, gf, ga, xf, xa in ((h, hg, ag, *xgs), (a, ag, hg, *xgs[::-1])):
                        key = (str(comp), team)
                        last_day[key] = day
                        diffs[key].append(float(xf - xa) if has_xg else float(gf - ga))
                        if has_xg:
                            luck[team].append(float((gf - ga) - (xf - xa)))
    return MatchContext(progress=progress, team=feats, rank=rank, points=points)
