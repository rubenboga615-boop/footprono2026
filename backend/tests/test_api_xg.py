"""xG Understat absents (site en panne) : remplacés par ceux d'API-Football, remis au
niveau Understat avec l'année précédente seulement (jamais de données futures)."""

import numpy as np

from footprono.engine.history import API_XG_MIN_MATCHES, History, fill_api_xg


def _hist(n: int, comp: str = "EPL") -> History:
    days = np.datetime64("2025-08-01", "D") + np.arange(n)
    return History(
        match_id=np.arange(1, n + 1, dtype=np.int64),
        competition=np.full(n, comp, dtype="<U12"),
        season=np.full(n, 2025, dtype=np.int64),
        date=days,
        home=np.ones(n, dtype=np.int64), away=np.full(n, 2, dtype=np.int64),
        finished=np.ones(n, dtype=bool), excluded=np.zeros(n, dtype=bool),
        hg=np.ones(n), ag=np.ones(n), hht=np.zeros(n), aht=np.zeros(n),
        hxg=np.full(n, 1.2), axg=np.full(n, 0.9),
    )  # fmt: skip


def test_missing_understat_filled_at_understat_level() -> None:
    n = API_XG_MIN_MATCHES + 20
    hist = _hist(n)
    api_h, api_a = np.full(n, 1.0), np.full(n, 0.75)  # 20 % plus bas qu'Understat
    hist.hxg[-10:] = hist.axg[-10:] = np.nan  # panne : dix derniers matchs
    api_h[-1] = api_a[-1] = np.nan  # ni Understat ni API-Football : reste vide
    api_h[-3] = 2.0  # un vrai écart reste un écart (même rapport pour tous)
    assert fill_api_xg(hist, api_h, api_a) == 9
    assert np.allclose(hist.hxg[-10:-3], 1.2)
    assert np.allclose(hist.axg[-10:-1], 0.9)
    assert np.isclose(hist.hxg[-3], 2.4)
    assert np.isnan(hist.hxg[-1])
    assert np.allclose(hist.hxg[:-10], 1.2)  # xG Understat jamais touchés


def test_scale_uses_only_past_matches_and_enough_of_them() -> None:
    n = API_XG_MIN_MATCHES + 1
    hist = _hist(n)
    api_h, api_a = np.full(n, 1.0), np.full(n, 0.75)
    api_h[-1] = api_a[-1] = 100.0  # absurde : ne doit pas peser sur son propre rapport
    hist.hxg[-1] = hist.axg[-1] = np.nan
    fill_api_xg(hist, api_h, api_a)
    assert np.isclose(hist.hxg[-1], 120.0)

    short = _hist(API_XG_MIN_MATCHES)  # pas assez de matchs pour estimer le rapport
    short.hxg[-1] = short.axg[-1] = np.nan
    assert fill_api_xg(short, np.ones(len(short)), np.ones(len(short))) == 0
    assert np.isnan(short.hxg[-1])
