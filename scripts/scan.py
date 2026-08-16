from src.config import DEFAULT_CONFIG
from src.data.market_data import download_market_data
from src.strategy.rotation import latest_scan

if __name__=="__main__":
    x=latest_scan(download_market_data(start="2023-01-01"),DEFAULT_CONFIG)
    print(x.to_string(index=False))
