from pathlib import Path
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from src.config import DEFAULT_CONFIG
from src.data.market_data import download_market_data
from src.strategy.rotation import latest_scan
from src.backtest.engine import run_backtest

app=FastAPI(title="ALPHABOT Rotation Research API",version="0.9.0"); DASHBOARD=Path(__file__).resolve().parent.parent/"static"/"index.html"
@app.get("/",include_in_schema=False)
def root():return FileResponse(DASHBOARD)
@app.get("/health")
def health():return {"ok":True,"service":"alphabot-v01","version":"0.9.0"}
@app.get("/api/scan")
def scan(start:str=Query(default="2023-01-01")):
    try:return {"strategy":"rotation-reversal","rows":latest_scan(download_market_data(start=start),DEFAULT_CONFIG).to_dict(orient="records")}
    except Exception as e:raise HTTPException(status_code=500,detail=str(e)) from e

def _serialize(r):
    e=r["equity"].reset_index();e=e.rename(columns={e.columns[0]:"date"});e["date"]=e["date"].dt.date.astype(str);t=r["trades"]
    return {"summary":r["summary"],"equity":e.tail(750).to_dict(orient="records"),"sector_contribution":r["sector_contribution"],"regime_breakdown":r["regime_breakdown"],"best_trades":r["best_trades"],"worst_trades":r["worst_trades"],"trades":[] if t.empty else t.to_dict(orient="records")[-100:]}
def _slice_market_data(data,start,end=None):return {s:(df.loc[df.index>=start].copy() if end is None else df.loc[(df.index>=start)&(df.index<end)].copy()) for s,df in data.items()}
def _baseline(data):return run_backtest(data,DEFAULT_CONFIG,entry_score_override=58,min_hold_trading_days=30,max_sectors_override=2,weighting="equal")
@app.get("/api/backtest")
def backtest(start:str=Query(default="2010-01-01"),end:str|None=Query(default=None)):
    try:return {"strategy":"rotation-reversal",**_serialize(run_backtest(download_market_data(start=start,end=end),DEFAULT_CONFIG))}
    except Exception as e:raise HTTPException(status_code=500,detail=str(e)) from e
@app.get("/api/portfolio-construction")
def portfolio_construction():
    try:
        d=download_market_data(start="2010-01-01");vs=[("1 sector equal",1,"equal"),("2 sectors equal",2,"equal"),("3 sectors equal",3,"equal"),("4 sectors equal",4,"equal"),("3 sectors inverse-vol",3,"inverse_vol"),("4 sectors inverse-vol",4,"inverse_vol")];results=[]
        for n,m,w in vs:results.append({"name":n,**_serialize(run_backtest(d,DEFAULT_CONFIG,entry_score_override=58,min_hold_trading_days=30,max_sectors_override=m,weighting=w))})
        return {"results":results,"best_sharpe":max(results,key=lambda x:x["summary"]["sharpe"])["name"],"best_return":max(results,key=lambda x:x["summary"]["strategy_total_return"])["name"],"lowest_drawdown":max(results,key=lambda x:x["summary"]["max_drawdown"])["name"]}
    except Exception as e:raise HTTPException(status_code=500,detail=str(e)) from e
@app.get("/api/validation")
def validation():
    try:
        data=download_market_data(start="2010-01-01"); full=_baseline(data); idx=full["equity"].index; first=int(idx.min().year); last=int(idx.max().year); yearly=[]
        for year in range(first,last+1):
            d=_slice_market_data(data,f"{year}-01-01",f"{year+1}-01-01")
            try:s=_baseline(d)["summary"]
            except Exception:continue
            yearly.append({"year":year,"strategy_return":s["strategy_total_return"],"spy_return":s["benchmark_total_return"],"alpha":s["strategy_total_return"]-s["benchmark_total_return"],"sharpe":s["sharpe"],"spy_sharpe":s["benchmark_sharpe"],"max_drawdown":s["max_drawdown"],"spy_max_drawdown":s["benchmark_max_drawdown"],"win_rate":s["win_rate"],"trades":s["number_of_trades"],"turnover":s["total_turnover"]})
        rolling=[]
        for years in [1,3]:
            for start_year in range(first,last-years+2):
                end_year=start_year+years;d=_slice_market_data(data,f"{start_year}-01-01",None if end_year>last else f"{end_year}-01-01")
                try:s=_baseline(d)["summary"]
                except Exception:continue
                rolling.append({"years":years,"start":start_year,"end":min(end_year-1,last),"strategy_return":s["strategy_total_return"],"spy_return":s["benchmark_total_return"],"alpha":s["strategy_total_return"]-s["benchmark_total_return"],"sharpe":s["sharpe"],"max_drawdown":s["max_drawdown"]})
        yvalid=[x for x in yearly if x["year"]<last]; one=[x for x in rolling if x["years"]==1];three=[x for x in rolling if x["years"]==3]
        stats={"positive_years":sum(x["strategy_return"]>0 for x in yvalid),"years_tested":len(yvalid),"beat_spy_years":sum(x["alpha"]>0 for x in yvalid),"losing_years":[x["year"] for x in yvalid if x["strategy_return"]<0],"worst_year":min(yvalid,key=lambda x:x["strategy_return"]) if yvalid else None,"positive_1y_windows":sum(x["strategy_return"]>0 for x in one),"one_year_windows":len(one),"positive_3y_windows":sum(x["strategy_return"]>0 for x in three),"three_year_windows":len(three),"beat_spy_3y_windows":sum(x["alpha"]>0 for x in three)}
        return {"experiment":"V0.9 retrospective validation","warning":"Historical data used during strategy development; this is retrospective robustness testing, not pristine out-of-sample validation.","frozen_rules":{"entry_threshold":58,"min_hold_trading_days":30,"max_sectors":2,"weighting":"equal","rebalance":"weekly"},"full_summary":full["summary"],"yearly":yearly,"rolling":rolling,"stats":stats}
    except Exception as e:raise HTTPException(status_code=500,detail=str(e)) from e
