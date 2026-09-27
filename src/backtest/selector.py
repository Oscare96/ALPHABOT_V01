"""Walk-forward strategy selection for research, with one shared portfolio.

Candidate histories are hypothetical net backtests. Selection reads only rows
before the decision date; the combined portfolio pays its own turnover costs.
"""

import pandas as pd

from src.backtest.catalogue_challenger import sector_momentum, summarize
from src.backtest.engine import run_backtest
from src.backtest.metrics import sharpe
from src.config import DEFAULT_CONFIG, SECTOR_ETFS


def select_portfolio(prices, candidate_weights, candidate_returns, *,
                     lookback=252, cost_bps=10.0):
    if lookback < 2 or cost_bps < 0 or not candidate_weights:
        raise ValueError("Invalid selector settings")
    dates = prices.index
    names = list(candidate_weights)
    if set(names) != set(candidate_returns) or dates.empty:
        raise ValueError("Candidate weights and returns must share a calendar")
    for name in names:
        if (not candidate_weights[name].index.equals(dates)
                or not candidate_weights[name].columns.equals(prices.columns)
                or not candidate_returns[name].index.equals(dates)):
            raise ValueError(f"Candidate {name} does not share the price calendar")
        weights = candidate_weights[name]
        if (weights.lt(0).any().any() or weights.sum(axis=1).gt(1.000001).any()
                or weights.isna().any().any()):
            raise ValueError(f"Candidate {name} exceeds long-only portfolio limits")

    first_exposure = []
    for name in names:
        active = candidate_weights[name].sum(axis=1).gt(0)
        if not active.any():
            raise ValueError(f"Candidate {name} has no historical positions")
        first_exposure.append(int(active.to_numpy().argmax()))
    earliest = max(first_exposure) + lookback

    target = pd.DataFrame(0.0, index=dates, columns=prices.columns)
    selected = pd.Series("cash", index=dates, dtype="object")
    decisions = []
    choice = "cash"
    quarter = None
    for i, date in enumerate(dates):
        key = (date.year, (date.month - 1) // 3)
        if key != quarter:
            quarter = key
            if i >= earliest:
                scores = {}
                for name in names:
                    past = candidate_returns[name].iloc[i - lookback:i]
                    if len(past) == lookback and past.notna().all() and (1 + past).prod() > 1:
                        scores[name] = sharpe(past)
                choice = max(scores, key=scores.get) if scores and max(scores.values()) > 0 else "cash"
                decisions.append({"date": date.date().isoformat(), "selected": choice,
                                  "trailing_sharpe": {k: round(float(v), 4)
                                                      for k, v in scores.items()}})
        if choice != "cash":
            target.loc[date] = candidate_weights[choice].loc[date]
        selected.loc[date] = choice

    # Signals at today's close govern tomorrow's close-to-close return.
    exposed = target.shift(1).fillna(0.0).gt(0)
    if ((exposed | target.gt(0)) & (~prices.gt(0))).any().any():
        raise ValueError("Missing or invalid price for an exposed portfolio position")
    daily = prices.ffill().pct_change(fill_method=None).fillna(0.0)
    gross = (target.shift(1).fillna(0.0) * daily).sum(axis=1)
    turnover = target.diff().fillna(target).abs().sum(axis=1)
    net = gross - turnover * cost_bps / 10000
    return {"returns": net, "weights": target, "selected": selected,
            "turnover": turnover, "decisions": decisions}


def research_selector(data):
    symbols = list(SECTOR_ETFS)
    baseline = run_backtest(data, DEFAULT_CONFIG, entry_score_override=58,
                            min_hold_trading_days=30, max_sectors_override=2,
                            position_cap=0.5)
    challenger = sector_momentum(data, symbols, top_n=2, lookback=252,
                                 position_cap=0.5, cost_bps=DEFAULT_CONFIG.trading_cost_bps)
    prices = pd.DataFrame({s: data[s]["close"] for s in symbols}).sort_index()
    if not baseline["weights"].index.equals(prices.index):
        raise ValueError("Candidate histories do not share a calendar")
    baseline_returns = baseline["equity"]["strategy"].pct_change().fillna(0.0)
    combined = select_portfolio(
        prices, {"rotation": baseline["weights"][symbols],
                 "sector_momentum": challenger["weights"]},
        {"rotation": baseline_returns, "sector_momentum": challenger["returns"]},
        cost_bps=DEFAULT_CONFIG.trading_cost_bps,
    )
    if not combined["decisions"]:
        raise ValueError("Not enough shared history to evaluate strategy selection")
    start = pd.Timestamp(combined["decisions"][0]["date"])
    result = {
        "start": start.date().isoformat(), "end": prices.index[-1].date().isoformat(),
        "rules": {"selection_frequency": "quarterly", "trailing_sessions": 252,
                  "positive_trailing_return_required": True,
                  "fallback": "cash", "cost_bps_per_unit_turnover": DEFAULT_CONFIG.trading_cost_bps},
        "rotation": summarize(baseline_returns.loc[start:]),
        "sector_momentum": summarize(challenger["returns"].loc[start:]),
        "spy_buy_and_hold": summarize(baseline["equity"]["spy"].pct_change().fillna(0.0).loc[start:]),
        "selected_portfolio": {**summarize(combined["returns"].loc[start:]),
                               "turnover": float(combined["turnover"].loc[start:].sum()),
                               "cash_days": int(combined["selected"].loc[start:].eq("cash").sum())},
        "decisions": combined["decisions"],
    }
    return result
