"""Run the research-only walk-forward selector on one historical dataset."""
import argparse
import json

from src.backtest.selector import research_selector
from src.data.market_data import download_market_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=None)
    args = parser.parse_args()
    print(json.dumps(research_selector(download_market_data(start=args.start,
                                                           end=args.end)), indent=2))
