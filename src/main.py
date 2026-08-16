from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from src.config import DEFAULT_CONFIG
from src.data.market_data import download_market_data
from src.strategy.rotation import latest_scan
from src.backtest.engine import run_backtest

app = FastAPI(title="ALPHABOT V01 Rotation Research API", version="0.6.0")
DASHBOARD = Path(__file__).resolve().parent.parent / "static" / "index.html"

@app.get("/", include_in_schema=False)
def root(): return FileResponse(DASHBOARD)

@app.get("/health")
def health(): return {"ok": True, "service": "alphabot-v01", "version": "0.6.0"}

@app.get("/api/scan")
def scan(start: str = Query(default="2023-01-01")):
    try:
        x = latest_scan(download_market_data(start=start), DEFAULT_CONFIG)
        return {"strategy": "rotation-reversal-v0.1", "rows": x.to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def _serialize(r):
    e = r["equity"].reset_index()
    e = e.rename(columns={e.columns[0]: "date"})
    e["date"] = e["date"].dt.date.astype(str)
    trades = r["trades"]
    return {"summary": r["summary"], "equity": e.tail(750).to_dict(orient="records"), "sector_contribution": r["sector_contribution"], "regime_breakdown": r["regime_breakdown"], "best_trades": r["best_trades"], "worst_trades": r["worst_trades"], "trades": [] if trades.empty else trades.to_dict(orient="records")[-100:]}


def _slice_market_data(data, start, end=None):
    sliced = {}
    for symbol, df in data.items():
        if end is None:
            part = df.loc[df.index >= start].copy()
        else:
            part = df.loc[(df.index >= start) & (df.index < end)].copy()
        sliced[symbol] = part
    return sliced

@app.get("/api/backtest")
def backtest(start: str = Query(default="2010-01-01"), end: str | None = Query(default=None)):
    try:
        data = download_market_data(start=start, end=end)
        return {"strategy": "rotation-reversal-v0.1", **_serialize(run_backtest(data, DEFAULT_CONFIG))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.get("/api/compare")
def compare(start: str = Query(default="2010-01-01"), end: str | None = Query(default=None)):
    try:
        data = download_market_data(start=start, end=end)
        return {"experiment": "V0.1 vs V0.2 RISK_ON-only entries", "v01": _serialize(run_backtest(data, DEFAULT_CONFIG)), "v02": _serialize(run_backtest(data, DEFAULT_CONFIG, entry_regime="RISK_ON"))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.get("/api/compare-exits")
def compare_exits(start: str = Query(default="2010-01-01"), end: str | None = Query(default=None)):
    try:
        data = download_market_data(start=start, end=end)
        return {"experiment": "V0.3 regime-aware exits", "v01": _serialize(run_backtest(data, DEFAULT_CONFIG)), "v03a": _serialize(run_backtest(data, DEFAULT_CONFIG, exit_policy="NON_RISK_ON")), "v03b": _serialize(run_backtest(data, DEFAULT_CONFIG, exit_policy="RISK_OFF"))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.get("/api/threshold-sensitivity")
def threshold_sensitivity(start: str = Query(default="2010-01-01"), end: str | None = Query(default=None)):
    try:
        data = download_market_data(start=start, end=end)
        thresholds = [60, 64, 68, 72, 76]
        results = []
        for threshold in thresholds:
            r = run_backtest(data, DEFAULT_CONFIG, entry_score_override=threshold)
            results.append({"threshold": threshold, **_serialize(r)})
        best = max(results, key=lambda x: x["summary"]["strategy_total_return"])
        return {"experiment": "V0.4 entry-threshold sensitivity", "thresholds": thresholds, "best_threshold": best["threshold"], "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.get("/api/threshold-stability")
def threshold_stability():
    try:
        thresholds = [56, 58, 60, 62, 64, 66]
        periods = [
            {"name": "2010-2014", "start": "2010-01-01", "end": "2015-01-01"},
            {"name": "2015-2019", "start": "2015-01-01", "end": "2020-01-01"},
            {"name": "2020-2022", "start": "2020-01-01", "end": "2023-01-01"},
            {"name": "2023-present", "start": "2023-01-01", "end": None},
        ]
        full_data = download_market_data(start="2010-01-01")
        full_results = []
        for threshold in thresholds:
            s = run_backtest(full_data, DEFAULT_CONFIG, entry_score_override=threshold)["summary"]
            full_results.append({"threshold": threshold, "summary": s})
        windows = []
        for period in periods:
            data = _slice_market_data(full_data, period["start"], period["end"])
            rows = []
            for threshold in thresholds:
                s = run_backtest(data, DEFAULT_CONFIG, entry_score_override=threshold)["summary"]
                rows.append({"threshold": threshold, "summary": s})
            windows.append({**period, "results": rows})
        stability = []
        for threshold in thresholds:
            window_returns = []
            window_sharpes = []
            positive_windows = 0
            for window in windows:
                row = next(x for x in window["results"] if x["threshold"] == threshold)
                ret = row["summary"]["strategy_total_return"]
                window_returns.append(ret)
                window_sharpes.append(row["summary"]["sharpe"])
                if ret > 0: positive_windows += 1
            full = next(x for x in full_results if x["threshold"] == threshold)["summary"]
            stability.append({"threshold": threshold, "positive_windows": positive_windows, "average_window_return": sum(window_returns) / len(window_returns), "worst_window_return": min(window_returns), "average_window_sharpe": sum(window_sharpes) / len(window_sharpes), "full_total_return": full["strategy_total_return"], "full_profit_factor": full["profit_factor"], "full_trades": full["number_of_trades"], "full_turnover": full["total_turnover"], "full_cost_drag": full["estimated_cost_drag_return_points"]})
        best_robust = max(stability, key=lambda x: (x["positive_windows"], x["worst_window_return"], x["average_window_return"]))
        return {"experiment": "V0.5 threshold stability by market era", "thresholds": thresholds, "full_results": full_results, "windows": windows, "stability": stability, "most_robust_threshold": best_robust["threshold"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.get("/api/churn-control")
def churn_control():
    try:
        data = download_market_data(start="2010-01-01")
        variants = [
            {"name": "Weekly control", "rebalance_weeks": 1, "min_hold_trading_days": 0},
            {"name": "2-week rebalance", "rebalance_weeks": 2, "min_hold_trading_days": 0},
            {"name": "4-week rebalance", "rebalance_weeks": 4, "min_hold_trading_days": 0},
            {"name": "Min hold 10d", "rebalance_weeks": 1, "min_hold_trading_days": 10},
            {"name": "Min hold 20d", "rebalance_weeks": 1, "min_hold_trading_days": 20},
        ]
        results = []
        for variant in variants:
            r = run_backtest(
                data,
                DEFAULT_CONFIG,
                entry_score_override=58,
                rebalance_weeks=variant["rebalance_weeks"],
                min_hold_trading_days=variant["min_hold_trading_days"],
            )
            results.append({**variant, **_serialize(r)})
        best = max(results, key=lambda x: x["summary"]["strategy_total_return"])
        lowest_turnover = min(results, key=lambda x: x["summary"]["total_turnover"])
        return {"experiment": "V0.6 churn control at threshold 58", "entry_threshold": 58, "best_total_return": best["name"], "lowest_turnover": lowest_turnover["name"], "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
