"""Print the two strategy signals without touching a broker account."""
import argparse
import json

from src.data.research_data import download_research_data
from src.strategy.shadow import scan_strategies


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--provider", choices=["yahoo", "alpaca_iex"], default="yahoo")
    args = parser.parse_args()
    report = scan_strategies(download_research_data(provider=args.provider,
                                                   start=args.start), as_of=args.as_of)
    report["data_provider"] = args.provider
    print(json.dumps(report, indent=2))
