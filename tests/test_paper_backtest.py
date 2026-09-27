import pandas as pd

from src.backtest import engine
from src.config import BENCHMARK, SECTOR_ETFS


def test_paper_position_cap_and_protected_hold(monkeypatch):
    dates = pd.bdate_range("2024-01-01", periods=45)
    data = {
        symbol: pd.DataFrame({"close": [100.0] * len(dates)}, index=dates)
        for symbol in [BENCHMARK, *SECTOR_ETFS]
    }
    rows = []
    for date in dates:
        for symbol in SECTOR_ETFS:
            first_week = date < dates[5]
            rows.append({
                "date": date,
                "symbol": symbol,
                "rotation_score": 80.0 if (symbol == "XLK" and first_week) or (symbol == "XLE" and not first_week) else 10.0,
                "eligible": (symbol == "XLK" and first_week) or (symbol == "XLE" and not first_week),
                "market_regime": "RISK_ON",
            })
    features = pd.DataFrame(rows).set_index("date")
    monkeypatch.setattr(engine, "build_features", lambda *_: features)

    result = engine.run_backtest(data, entry_score_override=58, max_sectors_override=1,
                                 min_hold_trading_days=30, position_cap=0.5)
    weights = result["weights"]
    assert weights.loc[dates[10], "XLK"] == 0.5
    assert weights.loc[dates[10], "XLE"] == 0.0
    assert weights.loc[dates[35], "XLE"] == 0.5
    assert result["summary"]["position_cap"] == 0.5
