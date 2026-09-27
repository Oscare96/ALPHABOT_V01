import pandas as pd
import pytest

from src.backtest.catalogue_challenger import sector_momentum


def test_monthly_signal_uses_prior_close_and_charges_turnover():
    dates = pd.bdate_range("2023-01-02", "2024-04-30")
    a = pd.Series(100.0, index=dates)
    b = pd.Series(100.0, index=dates)
    a.loc["2023-01-02":] = 110.0
    a.loc["2024-03-29":] = 120.0
    # A large move on rebalance day must not enter that morning's ranking.
    b.loc["2024-04-01":] = 200.0
    data = {"A": pd.DataFrame({"close": a}), "B": pd.DataFrame({"close": b})}
    result = sector_momentum(data, ["A", "B"], top_n=1, lookback=20,
                             position_cap=1.0, cost_bps=10)
    weights = result["weights"]
    assert weights.loc["2024-04-01", "A"] == 1.0
    assert weights.loc["2024-04-01", "B"] == 0.0
    assert weights.loc["2024-04-02", "A"] == 1.0
    assert result["returns"].loc["2024-04-01"] == pytest.approx(0.0)
    assert result["turnover"].loc["2024-04-01"] == pytest.approx(0.0)
    assert weights.loc["2024-04-01"].sum() <= 1.0


def test_entry_cost_and_next_day_exposure():
    dates = pd.bdate_range("2024-01-01", periods=25)
    prices = pd.Series([100.0] * 21 + [110.0] * 4, index=dates)
    data = {"A": pd.DataFrame({"close": prices})}
    result = sector_momentum(data, ["A"], top_n=1, lookback=2,
                             position_cap=1.0, cost_bps=10)
    first = result["weights"]["A"].gt(0)
    start = first[first].index[0]
    assert result["turnover"].loc[start] == pytest.approx(1.0)
    assert result["returns"].loc[start] == pytest.approx(-0.001)
