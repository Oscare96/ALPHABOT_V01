"""Compare the locked ALPHABOT baseline with a catalogue-inspired challenger."""
import argparse
import json

from src.backtest.catalogue_challenger import sector_momentum, summarize
from src.backtest.engine import run_backtest
from src.config import DEFAULT_CONFIG, SECTOR_ETFS
from src.data.market_data import download_market_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=None)
    args = parser.parse_args()
    data = download_market_data(start=args.start, end=args.end)
    baseline = run_backtest(data, DEFAULT_CONFIG, entry_score_override=58,
                            min_hold_trading_days=30, max_sectors_override=2,
                            position_cap=0.5)
    challenger = sector_momentum(data, list(SECTOR_ETFS), top_n=2, lookback=252,
                                 position_cap=0.5, cost_bps=DEFAULT_CONFIG.trading_cost_bps)
    first = challenger["weights"].sum(axis=1).gt(0)
    if not first.any():
        raise RuntimeError("Not enough overlapping history to test the challenger")
    shared_start = first[first].index[0]
    baseline_returns = baseline["equity"]["strategy"].pct_change().fillna(0).loc[shared_start:]
    challenger_returns = challenger["returns"].loc[shared_start:]
    benchmark_returns = baseline["equity"]["spy"].pct_change().fillna(0).loc[shared_start:]
    print(json.dumps({
        "evaluation_start": shared_start.date().isoformat(),
        "evaluation_end": challenger_returns.index[-1].date().isoformat(),
        "source": "awesome-systematic-trading/static/strategies/sector-momentum-rotational-system.py",
        "adaptation": "Original uses ten ETFs including VNQ and three equal positions; this uses ALPHABOT's 11 ETFs, two capped positions, prior-close 252-day momentum and monthly rebalance",
        "cost_bps_per_unit_turnover": DEFAULT_CONFIG.trading_cost_bps,
        "baseline": {**summarize(baseline_returns),
                     "turnover": float(baseline["turnover"].loc[shared_start:].sum()),
                     "exposure_days": int(baseline["weights"].loc[shared_start:].sum(axis=1).gt(0).sum())},
        "challenger": {**summarize(challenger_returns),
                       "turnover": float(challenger["turnover"].loc[shared_start:].sum()),
                       "exposure_days": int(challenger["weights"].loc[shared_start:].sum(axis=1).gt(0).sum())},
        "spy_buy_and_hold": summarize(benchmark_returns),
    }, indent=2))
