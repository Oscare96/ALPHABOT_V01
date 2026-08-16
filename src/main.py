from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from src.config import DEFAULT_CONFIG
from src.data.market_data import download_market_data
from src.strategy.rotation import latest_scan
from src.backtest.engine import run_backtest
app=FastAPI(title="ALPHABOT Rotation Research API",version="1.1.0");DASHBOARD=Path(__file__).resolve().parent.parent/"static"/"index.html"
@app.get("/",include_in_schema=False)
def root():return FileResponse(DASHBOARD)
@app.get("/health")
def health():return {"ok":True,"service":"alphabot","version":"1.1.0"}
@app.get("/api/scan")
def scan(start:str=Query(default="2023-01-01")):
    try:return {"rows":latest_scan(download_market_data(start=start),DEFAULT_CONFIG).to_dict("records")}
    except Exception as e:raise HTTPException(500,detail=str(e)) from e
def _slice(d,a,b=None):return {s:(x.loc[x.index>=a].copy() if b is None else x.loc[(x.index>=a)&(x.index<b)].copy()) for s,x in d.items()}
def _run(d,mode="none"):
    return run_backtest(d,DEFAULT_CONFIG,entry_score_override=58,min_hold_trading_days=30,max_sectors_override=2,weighting="equal",spy_fallback=(mode!="none"),spy_fallback_mode=("conditional" if mode=="conditional" else "always"))
@app.get("/api/conditional-fallback")
def conditional_fallback():
    try:
        d=download_market_data(start="2010-01-01");control=_run(d,"none");unconditional=_run(d,"always");conditional=_run(d,"conditional");years=[]
        first=int(control["equity"].index.min().year);last=int(control["equity"].index.max().year)
        for y in range(first,last+1):
            w=_slice(d,f"{y}-01-01",f"{y+1}-01-01")
            try:a=_run(w,"none")["summary"];u=_run(w,"always")["summary"];c=_run(w,"conditional")["summary"]
            except Exception:continue
            years.append({"year":y,"control":a["strategy_total_return"],"unconditional":u["strategy_total_return"],"conditional":c["strategy_total_return"],"spy":c["benchmark_total_return"],"conditional_vs_control":c["strategy_total_return"]-a["strategy_total_return"],"conditional_vs_spy":c["strategy_total_return"]-c["benchmark_total_return"],"conditional_dd":c["max_drawdown"],"conditional_sharpe":c["sharpe"],"fallback_time":c["fallback_time"]})
        cs=control["summary"];us=unconditional["summary"];xs=conditional["summary"];completed=max(0,len(years)-1)
        return {"experiment":"V1.1 conditional SPY fallback","rule":"When no sector setup exists, hold SPY only if SPY > 200-day MA and SPY 20-day return > 0; otherwise cash.","control":cs,"unconditional":us,"conditional":xs,"years":years,"summary":{"conditional_improves_return":xs["strategy_total_return"]>cs["strategy_total_return"],"conditional_improves_sharpe":xs["sharpe"]>cs["sharpe"],"conditional_improves_drawdown":xs["max_drawdown"]>cs["max_drawdown"],"years_conditional_beats_control":sum(x["conditional_vs_control"]>0 for x in years[:-1]),"years_conditional_beats_spy":sum(x["conditional_vs_spy"]>0 for x in years[:-1]),"completed_years":completed}}
    except Exception as e:raise HTTPException(500,detail=str(e)) from e
