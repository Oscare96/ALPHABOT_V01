from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx
from src.config import DEFAULT_CONFIG
from src.data.market_data import download_market_data
from src.strategy.rotation import latest_scan
from src.broker import alpaca

app=FastAPI(title="ALPHABOT Forward Validation API",version="1.2.0")
DASHBOARD=Path(__file__).resolve().parent.parent/"static"/"index.html"

class AlpacaCredentials(BaseModel):
    key_id: str
    secret_key: str

@app.get("/",include_in_schema=False)
def root(): return FileResponse(DASHBOARD)

@app.get("/health")
def health(): return {"ok":True,"service":"alphabot","version":"1.2.0","mode":"paper-forward-test"}

@app.get("/api/scan")
def scan(start:str=Query(default="2023-01-01")):
    try:
        rows=latest_scan(download_market_data(start=start),DEFAULT_CONFIG).to_dict("records")
        return {"strategy_locked":True,"rules":{"entry_threshold":58,"min_hold_trading_days":30,"max_sectors":2,"weighting":"equal","rebalance":"weekly","fallback":"cash"},"rows":rows}
    except Exception as e: raise HTTPException(500,detail=str(e)) from e

@app.get("/api/alpaca/status")
def alpaca_status():
    state=alpaca.configured()
    if not state["configured"]: return {**state,"connected":False}
    try:
        a=alpaca.account()
        return {**state,"connected":True,"account_status":a.get("status"),"account_number_tail":str(a.get("account_number", ""))[-4:]}
    except Exception as e: return {**state,"connected":False,"error":str(e)[:180]}

@app.post("/api/alpaca/connect")
def alpaca_connect(body:AlpacaCredentials):
    if not body.key_id.strip() or not body.secret_key.strip(): raise HTTPException(400,detail="Both Alpaca paper key and secret are required")
    alpaca.configure(body.key_id,body.secret_key)
    try:
        a=alpaca.account()
        return {"connected":True,"paper_only":True,"source":"runtime","account_status":a.get("status"),"account_number_tail":str(a.get("account_number", ""))[-4:],"note":"Credentials are held only in server memory. Add ALPACA_API_KEY and ALPACA_SECRET_KEY in Railway Variables for persistence across redeploys."}
    except httpx.HTTPStatusError as e:
        alpaca.clear_runtime_credentials(); raise HTTPException(401,detail="Alpaca rejected the paper credentials") from e
    except Exception as e:
        alpaca.clear_runtime_credentials(); raise HTTPException(502,detail=f"Could not reach Alpaca paper API: {str(e)[:160]}") from e

@app.get("/api/paper/account")
def paper_account():
    try:
        a=alpaca.account();p=alpaca.positions();o=alpaca.orders()
        return {"paper_only":True,"account":{"status":a.get("status"),"equity":a.get("equity"),"cash":a.get("cash"),"buying_power":a.get("buying_power"),"portfolio_value":a.get("portfolio_value"),"last_equity":a.get("last_equity")},"positions":p,"orders":o}
    except Exception as e: raise HTTPException(502,detail=str(e)[:200]) from e
