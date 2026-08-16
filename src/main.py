from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from src.config import DEFAULT_CONFIG
from src.data.market_data import download_market_data
from src.strategy.rotation import latest_scan
from src.backtest.engine import run_backtest
app=FastAPI(title="ALPHABOT Rotation Research API",version="1.0.0");DASHBOARD=Path(__file__).resolve().parent.parent/"static"/"index.html"
@app.get("/",include_in_schema=False)
def root():return FileResponse(DASHBOARD)
@app.get("/health")
def health():return {"ok":True,"service":"alphabot","version":"1.0.0"}
@app.get("/api/scan")
def scan(start:str=Query(default="2023-01-01")):
    try:return {"rows":latest_scan(download_market_data(start=start),DEFAULT_CONFIG).to_dict("records")}
    except Exception as e:raise HTTPException(500,detail=str(e)) from e
def _ser(r):return {"summary":r["summary"]}
def _slice(d,a,b=None):return {s:(x.loc[x.index>=a].copy() if b is None else x.loc[(x.index>=a)&(x.index<b)].copy()) for s,x in d.items()}
def _run(d,fallback=False):return run_backtest(d,DEFAULT_CONFIG,entry_score_override=58,min_hold_trading_days=30,max_sectors_override=2,weighting="equal",spy_fallback=fallback)
@app.get("/api/hybrid-validation")
def hybrid_validation():
    try:
        d=download_market_data(start="2010-01-01");control=_run(d,False);hybrid=_run(d,True);years=[]
        first=int(control["equity"].index.min().year);last=int(control["equity"].index.max().year)
        for y in range(first,last+1):
            w=_slice(d,f"{y}-01-01",f"{y+1}-01-01")
            try:a=_run(w,False)["summary"];h=_run(w,True)["summary"]
            except Exception:continue
            years.append({"year":y,"control":a["strategy_total_return"],"hybrid":h["strategy_total_return"],"spy":h["benchmark_total_return"],"hybrid_vs_control":h["strategy_total_return"]-a["strategy_total_return"],"hybrid_vs_spy":h["strategy_total_return"]-h["benchmark_total_return"],"hybrid_dd":h["max_drawdown"],"hybrid_sharpe":h["sharpe"],"fallback_time":h["fallback_time"]})
        hs=hybrid["summary"];cs=control["summary"]
        return {"experiment":"V1.0 SPY fallback","rules":{"threshold":58,"min_hold":30,"max_sectors":2,"weighting":"equal"},"control":cs,"hybrid":hs,"years":years,"summary":{"hybrid_improves_return":hs["strategy_total_return"]>cs["strategy_total_return"],"hybrid_improves_sharpe":hs["sharpe"]>cs["sharpe"],"hybrid_improves_drawdown":hs["max_drawdown"]>cs["max_drawdown"],"years_hybrid_beats_control":sum(x["hybrid_vs_control"]>0 for x in years[:-1]),"years_hybrid_beats_spy":sum(x["hybrid_vs_spy"]>0 for x in years[:-1]),"completed_years":max(0,len(years)-1)}}
    except Exception as e:raise HTTPException(500,detail=str(e)) from e
