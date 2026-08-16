import numpy as np
import pandas as pd

from src.config import BENCHMARK, DEFAULT_CONFIG, SECTOR_ETFS
from src.strategy.rotation import build_features
from src.backtest.metrics import cagr, max_drawdown, sharpe, sortino, annualized_volatility


def _first_trading_day_each_week(index):
    iso = index.isocalendar()
    keys = pd.Series(list(zip(iso.year, iso.week)), index=index)
    return ~keys.duplicated()


def _build_trade_ledger(effective_weights, prices, features):
    trades = []
    for symbol in effective_weights.columns:
        held = effective_weights[symbol] > 0
        starts = held & ~held.shift(1, fill_value=False)
        ends = ~held & held.shift(1, fill_value=False)
        start_dates = list(held.index[starts])
        end_dates = list(held.index[ends])

        if held.iloc[-1]:
            end_dates.append(held.index[-1])

        for entry_date in start_dates:
            exits_after = [d for d in end_dates if d >= entry_date]
            if not exits_after:
                continue
            exit_date = exits_after[0]
            exit_loc = prices.index.get_loc(exit_date)
            price_exit_date = prices.index[max(0, exit_loc - 1)] if not held.loc[exit_date] else exit_date

            entry_price = float(prices.loc[entry_date, symbol])
            exit_price = float(prices.loc[price_exit_date, symbol])
            trade_return = exit_price / entry_price - 1.0 if entry_price else 0.0
            holding_days = int((price_exit_date - entry_date).days)

            try:
                row = features.loc[entry_date]
                if isinstance(row, pd.Series):
                    row = row.to_frame().T
                entry_feature = row[row["symbol"] == symbol].iloc[0]
                entry_score = float(entry_feature["rotation_score"])
                regime = str(entry_feature["market_regime"])
                state = str(entry_feature["state"])
            except Exception:
                entry_score, regime, state = None, "UNKNOWN", "UNKNOWN"

            trades.append({
                "symbol": symbol,
                "sector": SECTOR_ETFS[symbol],
                "entry_date": entry_date.date().isoformat(),
                "exit_date": price_exit_date.date().isoformat(),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "return": float(trade_return),
                "holding_days": holding_days,
                "entry_score": entry_score,
                "entry_regime": regime,
                "entry_state": state,
            })

    return pd.DataFrame(trades)


def _trade_stats(trades):
    if trades.empty:
        return {
            "number_of_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "average_trade_return": 0.0,
            "average_winner": 0.0,
            "average_loser": 0.0,
            "average_holding_days": 0.0,
        }

    wins = trades[trades["return"] > 0]["return"]
    losses = trades[trades["return"] < 0]["return"]
    gross_profit = float(wins.sum())
    gross_loss = abs(float(losses.sum()))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

    return {
        "number_of_trades": int(len(trades)),
        "win_rate": float((trades["return"] > 0).mean()),
        "profit_factor": float(profit_factor),
        "average_trade_return": float(trades["return"].mean()),
        "average_winner": float(wins.mean()) if len(wins) else 0.0,
        "average_loser": float(losses.mean()) if len(losses) else 0.0,
        "average_holding_days": float(trades["holding_days"].mean()),
    }


def run_backtest(data, config=DEFAULT_CONFIG):
    features = build_features(data, config)
    prices = pd.DataFrame({s: data[s]["close"] for s in SECTOR_ETFS}).sort_index()
    spy = data[BENCHMARK]["close"].reindex(prices.index).ffill()

    # Be explicit about missing-price handling. This avoids pandas' deprecated
    # implicit forward-fill behavior and keeps the backtest deterministic.
    returns = prices.pct_change(fill_method=None).fillna(0.0)
    spy_returns = spy.pct_change(fill_method=None).fillna(0.0)
    equal_sector_returns = returns.mean(axis=1)
    dates = prices.index
    rebalance_mask = _first_trading_day_each_week(dates)

    current = pd.Series(0.0, index=prices.columns)
    weight_history = pd.DataFrame(0.0, index=dates, columns=prices.columns)
    turnover = pd.Series(0.0, index=dates)
    rebalance_count = 0

    for dt in dates:
        if rebalance_mask.loc[dt]:
            try:
                day = features.loc[dt].copy()
            except KeyError:
                weight_history.loc[dt] = current
                continue

            if isinstance(day, pd.Series):
                day = day.to_frame().T
            day = day.dropna(subset=["rotation_score", "symbol"])

            held_symbols = set(current[current > 0].index)
            holdable = day[
                day["symbol"].isin(held_symbols)
                & (day["rotation_score"] >= config.hold_score)
            ]
            entrants = day[
                day["eligible"]
                & (~day["symbol"].isin(held_symbols))
            ].sort_values("rotation_score", ascending=False)

            pool = pd.concat([holdable, entrants], ignore_index=True)
            pool = pool.sort_values("rotation_score", ascending=False)
            pool = pool.drop_duplicates("symbol").head(config.max_sectors)

            target = pd.Series(0.0, index=prices.columns)
            if len(pool):
                regime = str(pool.iloc[0]["market_regime"])
                gross_exposure = config.risk_off_size_multiplier if regime == "RISK_OFF" else 1.0
                target.loc[pool["symbol"].tolist()] = gross_exposure / len(pool)

            turnover.loc[dt] = float((target - current).abs().sum())
            current = target
            rebalance_count += 1

        weight_history.loc[dt] = current

    # Signals from day T are applied beginning on T+1, avoiding same-bar look-ahead.
    effective_weights = weight_history.shift(1).fillna(0.0)
    gross_returns = (effective_weights * returns).sum(axis=1)
    costs = turnover * (config.trading_cost_bps / 10000.0)
    strategy_returns = gross_returns - costs

    strategy_equity = (1.0 + strategy_returns).cumprod()
    spy_equity = (1.0 + spy_returns).cumprod()
    equal_sector_equity = (1.0 + equal_sector_returns).cumprod()

    gross_exposure = effective_weights.sum(axis=1)
    invested = gross_exposure > 0
    trades = _build_trade_ledger(effective_weights, prices, features)
    trade_stats = _trade_stats(trades)

    contributions = (effective_weights * returns).sum(axis=0).sort_values(ascending=False)
    sector_contribution = [
        {"symbol": s, "sector": SECTOR_ETFS[s], "return_contribution": float(v)}
        for s, v in contributions.items()
    ]

    # Group by the actual DatetimeIndex directly. Do not assume reset_index()
    # will name the resulting column "index" because yfinance may name it "Date".
    feature_regime = (
        features.groupby(level=0)["market_regime"]
        .first()
        .reindex(dates)
        .ffill()
    )
    regime_returns = []
    for regime in ["RISK_ON", "NEUTRAL", "RISK_OFF"]:
        mask = feature_regime == regime
        if mask.any():
            regime_returns.append({
                "regime": regime,
                "days": int(mask.sum()),
                "strategy_return_sum": float(strategy_returns.loc[mask].sum()),
                "average_daily_return": float(strategy_returns.loc[mask].mean()),
            })

    best_trades = [] if trades.empty else trades.nlargest(5, "return").to_dict(orient="records")
    worst_trades = [] if trades.empty else trades.nsmallest(5, "return").to_dict(orient="records")

    summary = {
        "start": strategy_equity.index.min().date().isoformat(),
        "end": strategy_equity.index.max().date().isoformat(),
        "strategy_total_return": float(strategy_equity.iloc[-1] - 1.0),
        "benchmark_total_return": float(spy_equity.iloc[-1] - 1.0),
        "equal_sector_total_return": float(equal_sector_equity.iloc[-1] - 1.0),
        "strategy_cagr": cagr(strategy_equity),
        "benchmark_cagr": cagr(spy_equity),
        "max_drawdown": max_drawdown(strategy_equity),
        "sharpe": sharpe(strategy_returns),
        "sortino": sortino(strategy_returns),
        "annualized_volatility": annualized_volatility(strategy_returns),
        "average_turnover": float(turnover.mean()),
        "number_of_rebalances": int(rebalance_count),
        "average_gross_exposure": float(gross_exposure.mean()),
        "time_in_market": float(invested.mean()),
        "cash_time": float((~invested).mean()),
        **trade_stats,
    }

    return {
        "summary": summary,
        "equity": pd.DataFrame({"strategy": strategy_equity, "spy": spy_equity, "equal_sectors": equal_sector_equity}),
        "weights": weight_history,
        "turnover": turnover,
        "trades": trades,
        "sector_contribution": sector_contribution,
        "regime_breakdown": regime_returns,
        "best_trades": best_trades,
        "worst_trades": worst_trades,
    }
