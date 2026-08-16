from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from src.config import DEFAULT_CONFIG
from src.data.market_data import download_market_data
from src.strategy.rotation import latest_scan
from src.backtest.engine import run_backtest

app=FastAPI(title="ALPHABOT Rotation Research API",version="0.8.0"); DASHBOARD=Path(__file__).resolve().parent.parent/"static"/"index.html"
@app.get("/",include_in_schema=False)
def root():return FileResponse(DASHBOARD)
@app.get("/health")
def health():return {"ok":True,"service":"alphabot-v01","version":"0.8.0"}
@app.get("/api/scan")
def scan(start:str=Query(default="2023-01-01")):
    try:return {"strategy":"rotation-reversal","rows":latest_scan(download_market_data(start=start),DEFAULT_CONFIG).to_dict(orient="records")}
    except Exception as e:raise HTTPException(status_code=500,detail=str(e)) from e

def _serialize(r):
    e=r["equity"].reset_index();e=e.rename(columns={e.columns[0]:"date"});e["date"]=e["date"].dt.date.astype(str);t=r["trades"]
    return {"summary":r["summary"],"equity":e.tail(750).to_dict(orient="records"),"sector_contribution":r["sector_contribution"],"regime_breakdown":r["regime_breakdown"],"best_trades":r["best_trades"],"worst_trades":r["worst_trades"],"trades":[] if t.empty else t.to_dict(orient="records")[-100:]}
def _slice_market_data(data,start,end=None):return {s:(df.loc[df.index>=start].copy() if end is None else df.loc[(df.index>=start)&(df.index<end)].copy()) for s,df in data.items()}
@app.get("/api/backtest")
def backtest(start:str=Query(default="2010-01-01"),end:str|None=Query(default=None)):
    try:return {"strategy":"rotation-reversal",**_serialize(run_backtest(download_market_data(start=start,end=end),DEFAULT_CONFIG))}
    except Exception as e:raise HTTPException(status_code=500,detail=str(e)) from e
@app.get("/api/compare")
def compare(start:str=Query(default="2010-01-01"),end:str|None=Query(default=None)):
    try:
        d=download_market_data(start=start,end=end);return {"v01":_serialize(run_backtest(d,DEFAULT_CONFIG)),"v02":_serialize(run_backtest(d,DEFAULT_CONFIG,entry_regime="RISK_ON"))}
    except Exception as e:raise HTTPException(status_code=500,detail=str(e)) from e
@app.get("/api/compare-exits")
def compare_exits(start:str=Query(default="2010-01-01"),end:str|None=Query(default=None)):
    try:
        d=download_market_data(start=start,end=end);return {"v01":_serialize(run_backtest(d,DEFAULT_CONFIG)),"v03a":_serialize(run_backtest(d,DEFAULT_CONFIG,exit_policy="NON_RISK_ON")),"v03b":_serialize(run_backtest(d,DEFAULT_CONFIG,exit_policy="RISK_OFF"))}
    except Exception as e:raise HTTPException(status_code=500,detail=str(e)) from e
@app.get("/api/threshold-sensitivity")
def threshold_sensitivity():
    try:
        d=download_market_data(start="2010-01-01");results=[{"threshold":t,**_serialize(run_backtest(d,DEFAULT_CONFIG,entry_score_override=t))} for t in [60,64,68,72,76]];best=max(results,key=lambda x:x["summary"]["strategy_total_return"]);return {"results":results,"best_threshold":best["threshold"]}
    except Exception as e:raise HTTPException(status_code=500,detail=str(e)) from e
@app.get("/api/threshold-stability")
def threshold_stability():
    try:
        ts=[56,58,60,62,64,66];periods=[("2010-2014","2010-01-01","2015-01-01"),("2015-2019","2015-01-01","2020-01-01"),("2020-2022","2020-01-01","2023-01-01"),("2023-present","2023-01-01",None)];d=download_market_data(start="2010-01-01");full=[{"threshold":t,"summary":run_backtest(d,DEFAULT_CONFIG,entry_score_override=t)["summary"]} for t in ts];windows=[]
        for n,a,b in periods:windows.append({"name":n,"results":[{"threshold":t,"summary":run_backtest(_slice_market_data(d,a,b),DEFAULT_CONFIG,entry_score_override=t)["summary"]} for t in ts]})
        stability=[]
        for t in ts:
            rr=[next(x for x in w["results"] if x["threshold"]==t)["summary"] for w in windows];f=next(x for x in full if x["threshold"]==t)["summary"];stability.append({"threshold":t,"positive_windows":sum(x["strategy_total_return"]>0 for x in rr),"average_window_return":sum(x["strategy_total_return"] for x in rr)/4,"worst_window_return":min(x["strategy_total_return"] for x in rr),"average_window_sharpe":sum(x["sharpe"] for x in rr)/4,"full_total_return":f["strategy_total_return"],"full_profit_factor":f["profit_factor"],"full_trades":f["number_of_trades"],"full_turnover":f["total_turnover"],"full_cost_drag":f["estimated_cost_drag_return_points"]})
        best=max(stability,key=lambda x:(x["positive_windows"],x["worst_window_return"],x["average_window_return"]));return {"thresholds":ts,"windows":windows,"stability":stability,"most_robust_threshold":best["threshold"]}
    except Exception as e:raise HTTPException(status_code=500,detail=str(e)) from e
@app.get("/api/churn-control")
def churn_control():
    try:
        d=download_market_data(start="2010-01-01");vs=[("Weekly control",1,0),("2-week rebalance",2,0),("4-week rebalance",4,0),("Min hold 10d",1,10),("Min hold 20d",1,20)];results=[{"name":n,**_serialize(run_backtest(d,DEFAULT_CONFIG,entry_score_override=58,rebalance_weeks=w,min_hold_trading_days=h))} for n,w,h in vs];return {"results":results,"best_total_return":max(results,key=lambda x:x["summary"]["strategy_total_return"])["name"],"lowest_turnover":min(results,key=lambda x:x["summary"]["total_turnover"])["name"]}
    except Exception as e:raise HTTPException(status_code=500,detail=str(e)) from e
@app.get("/api/hold-stability")
def hold_stability():
    try:
        hs=[0,5,10,15,20,25,30,40];periods=[("2010-2014","2010-01-01","2015-01-01"),("2015-2019","2015-01-01","2020-01-01"),("2020-2022","2020-01-01","2023-01-01"),("2023-present","2023-01-01",None)];d=download_market_data(start="2010-01-01");full=[{"hold_days":h,"summary":run_backtest(d,DEFAULT_CONFIG,entry_score_override=58,min_hold_trading_days=h)["summary"]} for h in hs];windows=[]
        for n,a,b in periods:windows.append({"name":n,"results":[{"hold_days":h,"summary":run_backtest(_slice_market_data(d,a,b),DEFAULT_CONFIG,entry_score_override=58,min_hold_trading_days=h)["summary"]} for h in hs]})
        st=[]
        for h in hs:
            rr=[next(x for x in w["results"] if x["hold_days"]==h)["summary"] for w in windows];f=next(x for x in full if x["hold_days"]==h)["summary"];st.append({"hold_days":h,"positive_periods":sum(x["strategy_total_return"]>0 for x in rr),"worst_period_return":min(x["strategy_total_return"] for x in rr),"full_total_return":f["strategy_total_return"],"full_gross_return":f["gross_strategy_total_return"],"full_cagr":f["strategy_cagr"],"full_max_drawdown":f["max_drawdown"],"full_sharpe":f["sharpe"],"full_profit_factor":f["profit_factor"],"full_trades":f["number_of_trades"],"full_turnover":f["total_turnover"],"full_cost_drag":f["estimated_cost_drag_return_points"],"full_time_in_market":f["time_in_market"],"full_average_hold":f["average_holding_days"]})
        robust=max(st,key=lambda x:(x["positive_periods"],x["worst_period_return"],x["full_sharpe"]));return {"hold_days":hs,"windows":windows,"stability":st,"most_robust_hold_days":robust["hold_days"],"best_full_return_hold_days":max(st,key=lambda x:x["full_total_return"])["hold_days"]}
    except Exception as e:raise HTTPException(status_code=500,detail=str(e)) from e
@app.get("/api/portfolio-construction")
def portfolio_construction():
    try:
        d=download_market_data(start="2010-01-01");variants=[("1 sector equal",1,"equal"),("2 sectors equal",2,"equal"),("3 sectors equal",3,"equal"),("4 sectors equal",4,"equal"),("3 sectors inverse-vol",3,"inverse_vol"),("4 sectors inverse-vol",4,"inverse_vol")];results=[]
        for n,m,w in variants:
            r=run_backtest(d,DEFAULT_CONFIG,entry_score_override=58,min_hold_trading_days=30,max_sectors_override=m,weighting=w);results.append({"name":n,**_serialize(r)})
        best_sharpe=max(results,key=lambda x:x["summary"]["sharpe"]);best_return=max(results,key=lambda x:x["summary"]["strategy_total_return"]);lowest_dd=max(results,key=lambda x:x["summary"]["max_drawdown"])
        return {"experiment":"V0.8 portfolio construction","baseline":{"entry_threshold":58,"min_hold_trading_days":30},"results":results,"best_sharpe":best_sharpe["name"],"best_return":best_return["name"],"lowest_drawdown":lowest_dd["name"]}
    except Exception as e:raise HTTPException(status_code=500,detail=str(e)) from e
