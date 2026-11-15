"""Jeu d'étude : prévisions hors échantillon du moteur + cotes de chaque bookmaker."""
import asyncio, pickle, sys
import numpy as np
from sqlalchemy import text
from footprono.core.config import get_settings
from footprono.db.session import create_engine, create_session_factory
from footprono.engine.history import load_history
from footprono.engine.backtest import BacktestConfig, run_backtest

async def main():
    eng = create_engine(get_settings())
    async with create_session_factory(eng)() as s:
        hist = await load_history(s)
        rows = (await s.execute(text(
            "select match_id, bookmaker, market, timing::text, selection, price from match_odds "
            "where market='1X2' or (market='OU' and line=2.5)"))).all()
    await eng.dispose()
    odds = {}
    for mid, book, market, timing, sel, price in rows:
        odds.setdefault(mid, {})[(book, market, timing, sel)] = float(price)
    from footprono.ingestion.reference import NON_LEAGUE_CODES
    comps = sorted(c for c in set(hist.competition[hist.finished]) if c not in NON_LEAGUE_CODES)
    print(comps, flush=True)
    pred = run_backtest(hist, BacktestConfig(competitions=comps, seasons=list(range(2018, 2027)),
                                              progress=lambda m: print(m, flush=True)))
    pickle.dump({"hist": hist, "pred": pred, "odds": odds}, open("/opt/fpdata/study/data_server.pkl", "wb"))
    print("ok", len(pred.match_id))
asyncio.run(main())
