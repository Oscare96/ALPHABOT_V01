"""Research-only sector momentum challenger from awesome-systematic-trading.

Source: static/strategies/sector-momentum-rotational-system.py. The adapted
variant uses ALPHABOT's 11-sector universe, two positions and 50% position cap.
No function in this module can submit broker orders.
"""

import pandas as pd

from src.backtest.metrics import cagr, max_drawdown, sharpe


def sector_momentum(data, symbols, top_n=2, lookback=252, position_cap=0.5,
                    cost_bps=10.0):
    if not symbols or top_n < 1 or lookback < 1 or position_cap <= 0 or cost_bps < 0:
        raise ValueError("Invalid momentum backtest settings")
    prices = pd.DataFrame({symbol: data[symbol]["close"] for symbol in symbols}).sort_index()
    dates = prices.index
    weights = pd.DataFrame(0.0, index=dates, columns=symbols)
    current = pd.Series(0.0, index=symbols)
    turnover = pd.Series(0.0, index=dates)
    month = None
    for i, date in enumerate(dates):
        if (date.year, date.month) != month:
            month = (date.year, date.month)
            if i > lookback:
                # Decide from the last completed day, before this month's first bar.
                momentum = prices.iloc[i - 1] / prices.iloc[i - 1 - lookback] - 1
                leaders = momentum.replace([float("inf"), -float("inf")], float("nan")).dropna().nlargest(top_n).index
                target = pd.Series(0.0, index=symbols)
                target.loc[leaders] = min(1.0 / top_n, position_cap)
                turnover.iloc[i] = (target - current).abs().sum()
                current = target
        weights.loc[date] = current

    # Stale closing prices carry forward for valuation, never forward into a signal.
    daily = prices.ffill().pct_change(fill_method=None).fillna(0.0)
    gross = (weights.shift(1).fillna(0.0) * daily).sum(axis=1)
    net = gross - turnover * cost_bps / 10000
    return {"returns": net, "weights": weights, "turnover": turnover}


def summarize(returns):
    equity = (1 + returns).cumprod()
    return {"total_return": float(equity.iloc[-1] - 1), "cagr": cagr(equity),
            "max_drawdown": max_drawdown(equity), "sharpe": sharpe(returns)}
