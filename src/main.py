from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from src.config import DEFAULT_CONFIG
from src.data.market_data import download_market_data
from src.strategy.rotation import latest_scan
from src.backtest.engine import run_backtest

app = FastAPI(title="ALPHABOT V01 Rotation Research API", version="0.1.2")
DASHBOARD = Path(__file__).resolve().parent.parent / "static" / "index.html"


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(DASHBOARD)


@app.get("/health")
def health():
    return {"ok": True, "service": "alphabot-v01", "version": "0.1.2"}


@app.get("/api/scan")
def scan(start: str = Query(default="2023-01-01")):
    try:
        x = latest_scan(download_market_data(start=start), DEFAULT_CONFIG)
        return {"strategy": "rotation-reversal-v0.1", "rows": x.to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/backtest")
def backtest(start: str = Query(default="2010-01-01"), end: str | None = Query(default=None)):
    try:
        r = run_backtest(download_market_data(start=start, end=end), DEFAULT_CONFIG)
        e = r["equity"].reset_index()
        e = e.rename(columns={e.columns[0]: "date"})
        e["date"] = e["date"].dt.date.astype(str)

        trades = r["trades"].copy()
        trade_rows = [] if trades.empty else trades.to_dict(orient="records")

        return {
            "strategy": "rotation-reversal-v0.1",
            "summary": r["summary"],
            "equity": e.tail(750).to_dict(orient="records"),
            "sector_contribution": r["sector_contribution"],
            "regime_breakdown": r["regime_breakdown"],
            "best_trades": r["best_trades"],
            "worst_trades": r["worst_trades"],
            "trades": trade_rows[-100:],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
