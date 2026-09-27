"""Historical adjusted ETF bars from Alpaca's IEX market-data feed.

Research opt-in only; this module cannot submit orders. IEX daily bars may
differ from the Yahoo data currently used by the paper executor.
"""

import os

import httpx
import pandas as pd

from src.config import BENCHMARK, SECTOR_ETFS

DATA_URL = "https://data.alpaca.markets/v2/stocks/bars"


def download_alpaca_market_data(start="2016-01-01", end=None, symbols=None):
    key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
    secret = os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("Alpaca paper market-data credentials are not configured")
    requested = list(symbols or [BENCHMARK, *SECTOR_ETFS])
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("Symbols must be a nonempty unique list")
    params = {"symbols": ",".join(requested), "timeframe": "1Day",
              "start": start, "adjustment": "all", "feed": "iex", "limit": 10000}
    if end:
        params["end"] = end
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    found = {s: [] for s in requested}
    tokens = set()
    with httpx.Client(timeout=30.0) as client:
        while True:
            response = client.get(DATA_URL, headers=headers, params=params)
            response.raise_for_status()
            page = response.json()
            for symbol, bars in page.get("bars", {}).items():
                if symbol in found:
                    found[symbol].extend(bars)
            token = page.get("next_page_token")
            if not token:
                break
            if token in tokens:
                raise RuntimeError("Repeated market-data pagination token")
            tokens.add(token)
            params["page_token"] = token
    result = {}
    for symbol, bars in found.items():
        if not bars:
            raise RuntimeError(f"No IEX historical bars for {symbol}")
        df = pd.DataFrame(bars).rename(columns={"o": "open", "h": "high", "l": "low",
                                               "c": "close", "v": "volume"})
        fields = ["open", "high", "low", "close", "volume"]
        if "t" not in df or any(field not in df for field in fields):
            raise RuntimeError(f"Incomplete IEX bars for {symbol}")
        dates = pd.to_datetime(df["t"], utc=True).dt.tz_convert("America/New_York").dt.normalize().dt.tz_localize(None)
        df = df[fields].apply(pd.to_numeric, errors="raise")
        df.index = pd.DatetimeIndex(dates)
        if df.index.has_duplicates or df[fields].isna().any().any() or (df["close"] <= 0).any():
            raise RuntimeError(f"Invalid or duplicate IEX bars for {symbol}")
        result[symbol] = df.sort_index()
    return result
