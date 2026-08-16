from __future__ import annotations
import pandas as pd
import yfinance as yf
from src.config import BENCHMARK, SECTOR_ETFS

def download_market_data(start="2005-01-01", end=None, symbols=None):
    requested = list(symbols or [BENCHMARK, *SECTOR_ETFS.keys()])
    raw = yf.download(requested, start=start, end=end, auto_adjust=True, progress=False, group_by="column", threads=True)
    if raw.empty:
        raise RuntimeError("Market data provider returned no data.")
    result = {}
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = set(map(str, raw.columns.get_level_values(0)))
        for symbol in requested:
            if symbol in level0:
                df = raw[symbol].copy()
            else:
                try:
                    df = raw.xs(symbol, axis=1, level=1).copy()
                except KeyError:
                    continue
            df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
            df.index = pd.to_datetime(df.index).tz_localize(None)
            result[symbol] = df.dropna(how="all").sort_index()
    else:
        df = raw.copy(); df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
        df.index = pd.to_datetime(df.index).tz_localize(None)
        result[requested[0]] = df.sort_index()
    missing = [s for s in requested if s not in result or result[s].empty]
    if missing:
        raise RuntimeError(f"Missing market data for: {', '.join(missing)}")
    return result
