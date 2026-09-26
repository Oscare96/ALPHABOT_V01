from dataclasses import replace
from pathlib import Path
import base64
import binascii
import hmac
import os

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import httpx

from src.config import DEFAULT_CONFIG
from src.data.market_data import download_market_data
from src.strategy.rotation import latest_scan
from src.broker import alpaca
from src.paper_executor import build_plan, execute_plan, journal

app = FastAPI(title="ALPHABOT Forward Validation API", version="1.3.0")
DASHBOARD = Path(__file__).resolve().parent.parent / "static" / "index.html"
LOCKED_CONFIG = replace(DEFAULT_CONFIG, entry_score=58.0)


@app.middleware("http")
async def require_dashboard_login(request: Request, call_next):
    # Railway needs an unauthenticated health check. Everything else, including
    # API docs and paper order endpoints, belongs to the same private dashboard.
    if request.url.path == "/health":
        return await call_next(request)
    username = os.getenv("ALPHABOT_DASHBOARD_USER")
    password = os.getenv("ALPHABOT_DASHBOARD_PASSWORD")
    if not username or not password:
        return JSONResponse({"detail": "Dashboard login is not configured"}, status_code=503)
    header = request.headers.get("authorization", "")
    try:
        scheme, encoded = header.split(" ", 1)
        supplied_user, supplied_password = base64.b64decode(encoded, validate=True).decode().split(":", 1)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        scheme, supplied_user, supplied_password = "", "", ""
    if not (scheme.lower() == "basic"
            and hmac.compare_digest(supplied_user, username)
            and hmac.compare_digest(supplied_password, password)):
        return JSONResponse(
            {"detail": "Dashboard login required"},
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="ALPHABOT"', "Cache-Control": "no-store"},
        )
    return await call_next(request)


class AlpacaCredentials(BaseModel):
    key_id: str
    secret_key: str


class ExecutePaperPlan(BaseModel):
    plan_id: str
    confirm_paper: bool = False


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(DASHBOARD)


@app.get("/health")
def health():
    return {"ok": True, "service": "alphabot", "version": "1.3.0", "mode": "paper-forward-test"}


@app.get("/api/scan")
def scan(start: str = Query(default="2023-01-01")):
    try:
        rows = latest_scan(download_market_data(start=start), LOCKED_CONFIG).to_dict("records")
        return {
            "strategy_locked": True,
            "rules": {
                "entry_threshold": 58,
                "hold_score": float(LOCKED_CONFIG.hold_score),
                "min_hold_trading_days": 30,
                "max_sectors": 2,
                "max_position_pct": 0.50,
                "weighting": "equal",
                "rebalance": "weekly",
                "fallback": "cash",
            },
            "rows": rows,
        }
    except Exception as e:
        raise HTTPException(500, detail=str(e)) from e


@app.get("/api/alpaca/status")
def alpaca_status():
    state = alpaca.configured()
    if not state["configured"]:
        return {**state, "connected": False}
    try:
        a = alpaca.account()
        return {
            **state,
            "connected": True,
            "account_status": a.get("status"),
            "account_number_tail": str(a.get("account_number", ""))[-4:],
        }
    except Exception as e:
        return {**state, "connected": False, "error": str(e)[:180]}


@app.post("/api/alpaca/connect")
def alpaca_connect(body: AlpacaCredentials):
    if not body.key_id.strip() or not body.secret_key.strip():
        raise HTTPException(400, detail="Both Alpaca paper key and secret are required")
    alpaca.configure(body.key_id, body.secret_key)
    try:
        a = alpaca.account()
        return {
            "connected": True,
            "paper_only": True,
            "source": "runtime",
            "account_status": a.get("status"),
            "account_number_tail": str(a.get("account_number", ""))[-4:],
            "note": "Credentials are held only in server memory. Add ALPACA_API_KEY and ALPACA_SECRET_KEY in Railway Variables for persistence across redeploys.",
        }
    except httpx.HTTPStatusError as e:
        alpaca.clear_runtime_credentials()
        raise HTTPException(401, detail="Alpaca rejected the paper credentials") from e
    except Exception as e:
        alpaca.clear_runtime_credentials()
        raise HTTPException(502, detail=f"Could not reach Alpaca paper API: {str(e)[:160]}") from e


@app.get("/api/paper/account")
def paper_account():
    try:
        a = alpaca.account()
        p = alpaca.positions()
        o = alpaca.orders()
        c = alpaca.clock()
        return {
            "paper_only": True,
            "market_open": bool(c.get("is_open")),
            "next_open": c.get("next_open"),
            "account": {
                "status": a.get("status"),
                "equity": a.get("equity"),
                "cash": a.get("cash"),
                "buying_power": a.get("buying_power"),
                "portfolio_value": a.get("portfolio_value"),
                "last_equity": a.get("last_equity"),
            },
            "positions": p,
            "orders": o,
        }
    except Exception as e:
        raise HTTPException(502, detail=str(e)[:200]) from e


@app.post("/api/paper/preview")
def paper_preview():
    try:
        return build_plan()
    except Exception as e:
        raise HTTPException(502, detail=str(e)[:260]) from e


@app.post("/api/paper/execute")
def paper_execute(body: ExecutePaperPlan):
    if not body.confirm_paper:
        raise HTTPException(400, detail="Paper execution confirmation is required")
    try:
        return execute_plan(body.plan_id)
    except RuntimeError as e:
        raise HTTPException(409, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(502, detail=str(e)[:260]) from e


@app.get("/api/paper/journal")
def paper_journal(limit: int = Query(default=50, ge=1, le=500)):
    return {"paper_only": True, "events": journal(limit)}
