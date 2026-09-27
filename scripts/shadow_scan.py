"""Print the two strategy signals without touching a broker account."""
import argparse
import json

from src.data.market_data import download_market_data
from src.strategy.shadow import scan_strategies


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--as-of", default=None)
    args = parser.parse_args()
    print(json.dumps(scan_strategies(download_market_data(start=args.start),
                                     as_of=args.as_of), indent=2))
