"""Read-only signals for comparing registered sector strategies.

This module deliberately has no broker import. A signal is not an order or a
strategy-performance ranking.
"""

from dataclasses import replace

import pandas as pd

from src.config import BENCHMARK, DEFAULT_CONFIG, SECTOR_ETFS
from src.strategy.rotation import latest_scan


def scan_strategies(data, as_of=None):
    symbols = [BENCHMARK, *SECTOR_ETFS]
    common_dates = None
    for symbol in symbols:
        if symbol not in data or "close" not in data[symbol]:
            raise ValueError(f"Missing closing prices for {symbol}")
        valid = data[symbol]["close"].dropna().index
        common_dates = valid if common_dates is None else common_dates.intersection(valid)
    common_dates = common_dates.sort_values()
    if as_of is not None:
        common_dates = common_dates[common_dates <= pd.Timestamp(as_of)]
    if len(common_dates) < 253:
        raise ValueError("Need 253 common completed daily bars for momentum")

    date = common_dates[-1]
    trimmed = {s: data[s].loc[:date] for s in symbols}
    prices = pd.DataFrame({s: trimmed[s]["close"].reindex(common_dates)
                           for s in SECTOR_ETFS})
    momentum = (prices.iloc[-1] / prices.iloc[-253] - 1).sort_values(ascending=False)
    if not (prices.iloc[-1] > 0).all() or not (prices.iloc[-253] > 0).all():
        raise ValueError("Sector closing prices must be positive")
    rotation = latest_scan(trimmed, replace(DEFAULT_CONFIG, entry_score=58.0))
    eligible = rotation[rotation["eligible"]].head(2)
    return {
        "as_of": date.date().isoformat(),
        "mode": "shadow_only",
        "strategies": [
            {"id": "rotation", "candidates": eligible["symbol"].tolist(),
             "regime": str(rotation.iloc[0]["market_regime"]),
             "scores": {row.symbol: round(float(row.rotation_score), 2)
                        for row in rotation.itertuples()}},
            {"id": "sector_momentum", "candidates": momentum.head(2).index.tolist(),
             "lookback_sessions": 252,
             "scores": {s: round(float(v), 6) for s, v in momentum.items()}},
        ],
        "selector": {"status": "unvalidated", "selected_strategy": None,
                     "reason": "No forward performance record or validated walk-forward selector"},
    }
