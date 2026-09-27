"""Run the research-only walk-forward selector on one historical dataset."""
import argparse
import json

from src.backtest.selector import research_selector
from src.data.research_data import download_research_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--provider", choices=["yahoo", "alpaca_iex"], default="yahoo")
    args = parser.parse_args()
    result = research_selector(download_research_data(provider=args.provider,
                                                     start=args.start, end=args.end))
    result["data_provider"] = args.provider
    print(json.dumps(result, indent=2))
