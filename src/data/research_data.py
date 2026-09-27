"""Explicit choice of research data feed; never silently mix feeds."""

from src.data.alpaca_market_data import download_alpaca_market_data
from src.data.market_data import download_market_data


def download_research_data(*, provider="yahoo", start="2016-01-01", end=None):
    if provider == "yahoo":
        return download_market_data(start=start, end=end)
    if provider == "alpaca_iex":
        return download_alpaca_market_data(start=start, end=end)
    raise ValueError(f"Unknown research data provider: {provider}")
