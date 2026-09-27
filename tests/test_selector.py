import pandas as pd
import pytest

from src.backtest.selector import select_portfolio


def test_selector_uses_prior_window_and_charges_strategy_switch():
    dates = pd.bdate_range("2024-01-01", "2024-07-10")
    prices = pd.DataFrame({"A": 100.0, "B": 100.0}, index=dates)
    aw = pd.DataFrame({"A": 1.0, "B": 0.0}, index=dates)
    bw = pd.DataFrame({"A": 0.0, "B": 1.0}, index=dates)
    ar = pd.Series([0.01 + (i % 2) * 0.002 for i in range(len(dates))], index=dates)
    br = pd.Series([-0.01 - (i % 2) * 0.002 for i in range(len(dates))], index=dates)
    ar.loc["2024-06-20":] = [-0.01 - (i % 2) * 0.002 for i in range(len(ar.loc["2024-06-20":]))]
    br.loc["2024-06-20":] = [0.03 + (i % 2) * 0.002 for i in range(len(br.loc["2024-06-20":]))]
    # A large *same-day* B return must not influence the April selection.
    br.loc["2024-04-01"] = 0.9
    result = select_portfolio(prices, {"A": aw, "B": bw},
                              {"A": ar, "B": br}, lookback=3, cost_bps=10)
    assert result["selected"].loc["2024-04-01"] == "A"
    assert result["selected"].loc["2024-07-01"] == "B"
    assert result["turnover"].loc["2024-04-01"] == pytest.approx(1.0)
    assert result["turnover"].loc["2024-07-01"] == pytest.approx(2.0)
    assert result["returns"].loc["2024-07-01"] == pytest.approx(-0.002)
    assert result["decisions"][-1]["selected"] == "B"


def test_selector_rejects_leveraged_candidate():
    dates = pd.bdate_range("2024-01-01", periods=15)
    prices = pd.DataFrame({"A": 100.0}, index=dates)
    weights = pd.DataFrame({"A": 1.2}, index=dates)
    returns = pd.Series(0.01, index=dates)
    with pytest.raises(ValueError, match="long-only"):
        select_portfolio(prices, {"A": weights}, {"A": returns}, lookback=3)


def test_selector_rejects_missing_price_for_held_position():
    dates = pd.bdate_range("2024-01-01", "2024-04-10")
    prices = pd.DataFrame({"A": 100.0}, index=dates)
    prices.loc["2024-04-02", "A"] = float("nan")
    weights = pd.DataFrame({"A": 1.0}, index=dates)
    returns = pd.Series([0.01 + i % 2 * 0.002 for i in range(len(dates))], index=dates)
    with pytest.raises(ValueError, match="Missing or invalid price"):
        select_portfolio(prices, {"A": weights}, {"A": returns}, lookback=3)
