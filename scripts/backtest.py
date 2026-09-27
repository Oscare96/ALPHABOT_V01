import argparse,json
from src.config import DEFAULT_CONFIG
from src.data.market_data import download_market_data
from src.backtest.engine import run_backtest

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--start",default="2010-01-01"); p.add_argument("--end",default=None); p.add_argument("--paper-rules",action="store_true",help="Use the locked Alpaca paper strategy settings"); a=p.parse_args()
    settings = {"entry_score_override": 58.0, "max_sectors_override": 2, "min_hold_trading_days": 30, "position_cap": 0.50} if a.paper_rules else {}
    result=run_backtest(download_market_data(start=a.start,end=a.end),DEFAULT_CONFIG,**settings)
    print(json.dumps(result["summary"],indent=2))
