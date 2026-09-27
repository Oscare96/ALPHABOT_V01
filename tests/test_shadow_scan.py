import pandas as pd
import pytest

from src.config import BENCHMARK, SECTOR_ETFS
from src.strategy.shadow import scan_strategies


def test_shadow_scan_ranks_momentum_without_selecting_an_executor():
    dates = pd.bdate_range("2023-01-02", periods=310)
    data = {}
    for symbol in [BENCHMARK, *SECTOR_ETFS]:
        close = pd.Series(100.0, index=dates)
        if symbol == "XLK":
            close.iloc[10:] = pd.Series(range(100, 400), index=dates[10:])
        elif symbol == "XLE":
            close.iloc[10:] = pd.Series(range(100, 400), index=dates[10:]) / 2 + 50
        data[symbol] = pd.DataFrame({"close": close, "high": close + 1,
                                     "low": close - 1, "volume": 1000000.0})
    as_of = dates[-2]
    report = scan_strategies(data, as_of=as_of)
    assert report["as_of"] == as_of.date().isoformat()
    assert report["strategies"][1]["candidates"] == ["XLK", "XLE"]
    assert report["selector"]["selected_strategy"] is None
    assert report["mode"] == "shadow_only"


def test_shadow_scan_requires_common_history():
    dates = pd.bdate_range("2024-01-01", periods=252)
    data = {symbol: pd.DataFrame({"close": 100.0}, index=dates)
            for symbol in [BENCHMARK, *SECTOR_ETFS]}
    with pytest.raises(ValueError, match="253 common"):
        scan_strategies(data)
