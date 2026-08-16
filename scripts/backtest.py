import argparse,json
from src.config import DEFAULT_CONFIG
from src.data.market_data import download_market_data
from src.backtest.engine import run_backtest

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--start",default="2010-01-01"); p.add_argument("--end",default=None); a=p.parse_args()
    result=run_backtest(download_market_data(start=a.start,end=a.end),DEFAULT_CONFIG)
    print(json.dumps(result["summary"],indent=2))
