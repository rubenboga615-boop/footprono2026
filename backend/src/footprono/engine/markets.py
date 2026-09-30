"""Marchés dérivés de la distribution des scores.

Chaque sélection est décrite par la probabilité de ses issues de règlement :
gagné, demi-gagné, remboursé, demi-perdu, perdu (les demi-issues n'existent
que pour les handicaps asiatiques à quart de but). La cote juste est celle qui
rend l'espérance nulle.

Clés : ``marché|ligne|sélection`` (ligne vide si sans objet), par exemple
``1X2||home``, ``OU|2.5|over``, ``AH|-0.75|home``, ``HTFT||home/draw``.
"""

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from footprono.engine.scores import ScoreDistribution

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
BoolArray = NDArray[np.bool_]

OU_LINES = (0.5, 1.5, 2.5, 3.5, 4.5, 5.5)
TEAM_OU_LINES = (0.5, 1.5, 2.5, 3.5)
HT_OU_LINES = (0.5, 1.5, 2.5)
AH_LINES = tuple(x / 4 for x in range(-12, 13))  # -3 à +3 par quart de but
EH_LINES = (-2, -1, 1, 2)
COMBO_OU_LINES = (1.5, 2.5, 3.5)
EXACT_MAX = 5


@dataclass(frozen=True)
class Selection:
    win: float
    half_win: float = 0.0
    push: float = 0.0
    half_loss: float = 0.0

    @property
    def loss(self) -> float:
        return max(0.0, 1.0 - self.win - self.half_win - self.push - self.half_loss)

    @property
    def effective_probability(self) -> float:
        """Probabilité « équivalente » : 1 / cote juste (remboursements neutralisés)."""
        gain = self.win + self.half_win / 2
        lost = self.loss + self.half_loss / 2
        return gain / (gain + lost) if gain + lost > 0 else 0.5

    def expected_return(self, price: float) -> float:
        """Gain moyen pour 1 misé à la cote ``price`` (0 = neutre)."""
        return (self.win + self.half_win / 2) * (price - 1) - self.loss - self.half_loss / 2

    @property
    def fair_odds(self) -> float | None:
        """Cote d'espérance nulle ; None si la sélection ne peut pas gagner."""
        gain = self.win + self.half_win / 2
        if gain <= 0:
            return None
        return 1 + (self.loss + self.half_loss / 2) / gain


def _line_key(x: float) -> str:
    return f"{x:g}"


def asian_handicap(ft: FloatArray, margin: IntArray, line: float) -> Selection:
    """Handicap asiatique ; ``margin`` = buts de l'équipe choisie - buts adverses."""
    if (line * 4) % 2 == 1:  # quart de but : moitié de la mise sur chaque ligne voisine
        lo, hi = margin + line - 0.25, margin + line + 0.25
        return Selection(
            win=float(ft[(lo > 0) & (hi > 0)].sum()),
            half_win=float(ft[(lo == 0) & (hi > 0)].sum()),
            half_loss=float(ft[(lo < 0) & (hi == 0)].sum()),
        )
    d = margin + line
    return Selection(win=float(ft[d > 0].sum()), push=float(ft[d == 0].sum()))


def derive_markets(dist: ScoreDistribution) -> dict[str, Selection]:
    ft, ht, joint = dist.full_time, dist.half_time, dist.joint
    out: dict[str, Selection] = {}

    def put(market: str, line: str, sel: str, s: Selection | float) -> None:
        out[f"{market}|{line}|{sel}"] = s if isinstance(s, Selection) else Selection(win=float(s))

    def p(mask: BoolArray) -> float:
        return float(ft[mask].sum())

    h, a = (np.asarray(x, dtype=np.int64) for x in np.indices(ft.shape))
    total = h + a
    results: dict[str, BoolArray] = {"home": h > a, "draw": h == a, "away": h < a}
    home, draw, away = (p(results[k]) for k in ("home", "draw", "away"))
    for sel, mask in results.items():
        put("1X2", "", sel, p(mask))
    put("DC", "", "1X", home + draw)
    put("DC", "", "X2", draw + away)
    put("DC", "", "12", home + away)
    put("DNB", "", "home", Selection(win=home, push=draw))
    put("DNB", "", "away", Selection(win=away, push=draw))

    for line in OU_LINES:
        over = p(total > line)
        put("OU", _line_key(line), "over", over)
        put("OU", _line_key(line), "under", 1 - over)
    for side, goals in (("HOME", h), ("AWAY", a)):
        for line in TEAM_OU_LINES:
            over = p(goals > line)
            put(f"TEAM_OU_{side}", _line_key(line), "over", over)
            put(f"TEAM_OU_{side}", _line_key(line), "under", 1 - over)

    both = (h > 0) & (a > 0)
    put("BTTS", "", "yes", p(both))
    put("BTTS", "", "no", 1 - p(both))

    other = 1.0
    for i in range(EXACT_MAX + 1):
        for j in range(EXACT_MAX + 1):
            put("CS", "", f"{i}-{j}", float(ft[i, j]))
            other -= float(ft[i, j])
    put("CS", "", "other", max(other, 0.0))

    put("CLEAN_SHEET", "", "home", p(a == 0))
    put("CLEAN_SHEET", "", "away", p(h == 0))
    put("WIN_TO_NIL", "", "home", p((h > a) & (a == 0)))
    put("WIN_TO_NIL", "", "away", p((a > h) & (h == 0)))
    for k in (1, 2):
        put("MARGIN", "", f"home+{k}", p(h - a == k))
        put("MARGIN", "", f"away+{k}", p(a - h == k))
    put("MARGIN", "", "home+3", p(h - a >= 3))
    put("MARGIN", "", "away+3", p(a - h >= 3))
    put("MARGIN", "", "draw", draw)
    even = p(total % 2 == 0)
    put("ODD_EVEN", "", "even", even)
    put("ODD_EVEN", "", "odd", 1 - even)

    for line in AH_LINES:
        put("AH", _line_key(line), "home", asian_handicap(ft, h - a, line))
        put("AH", _line_key(line), "away", asian_handicap(ft, a - h, -line))
    for eh in EH_LINES:  # handicap européen (3 issues)
        put("EH", _line_key(eh), "home", p(h + eh > a))
        put("EH", _line_key(eh), "draw", p(h + eh == a))
        put("EH", _line_key(eh), "away", p(h + eh < a))

    # Combinés dans le même match : probabilité jointe exacte.
    for res, rmask in results.items():
        for line in COMBO_OU_LINES:
            put("1X2_OU", _line_key(line), f"{res}/over", p(rmask & (total > line)))
            put("1X2_OU", _line_key(line), f"{res}/under", p(rmask & (total < line)))
        put("1X2_BTTS", "", f"{res}/yes", p(rmask & both))
        put("1X2_BTTS", "", f"{res}/no", p(rmask & ~both))

    # Mi-temps.
    hh, ha = (np.asarray(x, dtype=np.int64) for x in np.indices(ht.shape))
    ht_results: dict[str, BoolArray] = {"home": hh > ha, "draw": hh == ha, "away": hh < ha}
    for sel, mask in ht_results.items():
        put("HT_1X2", "", sel, float(ht[mask].sum()))
    for line in HT_OU_LINES:
        over = float(ht[hh + ha > line].sum())
        put("HT_OU", _line_key(line), "over", over)
        put("HT_OU", _line_key(line), "under", 1 - over)
    ht_both = float(ht[(hh > 0) & (ha > 0)].sum())
    put("HT_BTTS", "", "yes", ht_both)
    put("HT_BTTS", "", "no", 1 - ht_both)

    # Loi jointe : indices (mi-temps domicile, mi-temps extérieur, final domicile, final extérieur).
    jhh, jha, jfh, jfa = np.indices(joint.shape)
    joint_ht = {"home": jhh > jha, "draw": jhh == jha, "away": jhh < jha}
    joint_ft = {"home": jfh > jfa, "draw": jfh == jfa, "away": jfh < jfa}
    for hs, hmask in joint_ht.items():
        for fs, fmask in joint_ft.items():
            put("HTFT", "", f"{hs}/{fs}", float(joint[hmask & fmask].sum()))
    first, second = jhh + jha, (jfh - jhh) + (jfa - jha)
    put("HIGHEST_HALF", "", "first", float(joint[first > second].sum()))
    put("HIGHEST_HALF", "", "second", float(joint[second > first].sum()))
    put("HIGHEST_HALF", "", "equal", float(joint[first == second].sum()))
    return out


def iter_market(markets: dict[str, Selection], market: str) -> Iterator[tuple[str, str, Selection]]:
    prefix = market + "|"
    for key, sel in markets.items():
        if key.startswith(prefix):
            _, line, name = key.split("|")
            yield line, name, sel
