from dataclasses import replace
import numpy as np
import pandas as pd
from src.config import BENCHMARK, DEFAULT_CONFIG, SECTOR_ETFS
from src.strategy.rotation import build_features
from src.backtest.metrics import cagr, max_drawdown, sharpe, sortino, annualized_volatility

def _rebalance_mask(index,rebalance_weeks=1):
    iso=index.isocalendar();keys=pd.Series(list(zip(iso.year,iso.week)),index=index);weekly=index[~keys.duplicated()];return pd.Series(index.isin(set(weekly[::rebalance_weeks])),index=index)
def _trade_stats(t):
    if t.empty:return {"number_of_trades":0,"win_rate":0.0,"profit_factor":0.0,"average_trade_return":0.0,"average_winner":0.0,"average_loser":0.0,"average_holding_days":0.0}
    w=t[t["return"]>0]["return"];l=t[t["return"]<0]["return"];gp=float(w.sum());gl=abs(float(l.sum()));return {"number_of_trades":len(t),"win_rate":float((t["return"]>0).mean()),"profit_factor":gp/gl if gl else 999.0 if gp else 0.0,"average_trade_return":float(t["return"].mean()),"average_winner":float(w.mean()) if len(w) else 0.0,"average_loser":float(l.mean()) if len(l) else 0.0,"average_holding_days":float(t["holding_days"].mean())}
def _ledger(weights,prices):
    out=[]
    for s in weights.columns:
        held=weights[s]>0;starts=held&~held.shift(1,fill_value=False);ends=~held&held.shift(1,fill_value=False);ed=list(weights.index[ends]);
        if held.iloc[-1]:ed.append(weights.index[-1])
        for a in weights.index[starts]:
            z=next((x for x in ed if x>=a),None)
            if z is None:continue
            pxz=weights.index[max(0,weights.index.get_loc(z)-1)] if not held.loc[z] else z;pa=float(prices.loc[a,s]);pz=float(prices.loc[pxz,s]);out.append({"symbol":s,"entry_date":a.date().isoformat(),"exit_date":pxz.date().isoformat(),"return":pz/pa-1 if pa else 0,"holding_days":int((pxz-a).days)})
    return pd.DataFrame(out)
def _target(syms,gross,returns,dt,weighting):
    if not syms:return pd.Series(dtype=float)
    if weighting=="equal":return pd.Series(gross/len(syms),index=syms)
    v=returns.loc[:dt,syms].tail(20).std().replace(0,np.nan);inv=(1/v).replace([np.inf,-np.inf],np.nan).dropna();return gross*inv/inv.sum() if len(inv)==len(syms) and inv.sum()>0 else pd.Series(gross/len(syms),index=syms)
def run_backtest(data,config=DEFAULT_CONFIG,entry_regime=None,exit_policy=None,entry_score_override=None,rebalance_weeks=1,min_hold_trading_days=0,max_sectors_override=None,weighting="equal",spy_fallback=False):
    cfg=replace(config,entry_score=float(entry_score_override)) if entry_score_override is not None else config;maxs=int(max_sectors_override or cfg.max_sectors);features=build_features(data,cfg);sector_prices=pd.DataFrame({s:data[s]["close"] for s in SECTOR_ETFS}).sort_index();spy=data[BENCHMARK]["close"].reindex(sector_prices.index).ffill();prices=sector_prices.copy();prices[BENCHMARK]=spy;returns=prices.pct_change(fill_method=None).fillna(0);spyret=returns[BENCHMARK];dates=prices.index;mask=_rebalance_mask(dates,rebalance_weeks);cols=list(SECTOR_ETFS)+([BENCHMARK] if spy_fallback else []);current=pd.Series(0.0,index=cols);wh=pd.DataFrame(0.0,index=dates,columns=cols);turn=pd.Series(0.0,index=dates);entry_loc={};rebs=0;fallback_days=0
    for loc,dt in enumerate(dates):
        if mask.loc[dt]:
            try:day=features.loc[dt].copy()
            except KeyError:wh.loc[dt]=current;continue
            if isinstance(day,pd.Series):day=day.to_frame().T
            day=day.dropna(subset=["rotation_score","symbol"]);regime=str(day.iloc[0]["market_regime"]) if len(day) else "UNKNOWN";held={s for s in SECTOR_ETFS if current.get(s,0)>0};protected={s for s in held if min_hold_trading_days and loc-entry_loc.get(s,loc)<min_hold_trading_days};normal=day[day["symbol"].isin(held)&(day["rotation_score"]>=cfg.hold_score)];ph=day[day["symbol"].isin(protected)];holdable=pd.concat([normal,ph]).drop_duplicates("symbol");entrants=day[day["eligible"]&~day["symbol"].isin(held)].sort_values("rotation_score",ascending=False);pool=pd.concat([holdable,entrants]).sort_values("rotation_score",ascending=False).drop_duplicates("symbol").head(maxs);target=pd.Series(0.0,index=cols)
            if len(pool):
                gross=cfg.risk_off_size_multiplier if regime=="RISK_OFF" else 1.0;syms=pool["symbol"].tolist();target.loc[syms]=_target(syms,gross,returns,dt,weighting)
            elif spy_fallback:target.loc[BENCHMARK]=1.0
            new={s for s in SECTOR_ETFS if target.get(s,0)>0}-held;exited=held-{s for s in SECTOR_ETFS if target.get(s,0)>0}
            for s in new:entry_loc[s]=loc
            for s in exited:entry_loc.pop(s,None)
            turn.loc[dt]=float((target-current).abs().sum());current=target;rebs+=1
        wh.loc[dt]=current
    ew=wh.shift(1).fillna(0);fallback_exposure=ew[BENCHMARK] if spy_fallback else pd.Series(0.0,index=dates);fallback_days=int((fallback_exposure>0).sum());gross=(ew*returns[cols]).sum(axis=1);cost=turn*(cfg.trading_cost_bps/10000);net=gross-cost;eq=(1+net).cumprod();geq=(1+gross).cumprod();spyeq=(1+spyret).cumprod();exposure=ew.sum(axis=1);trades=_ledger(ew[SECTOR_ETFS.keys()],sector_prices);stats=_trade_stats(trades);summary={"start":dates.min().date().isoformat(),"end":dates.max().date().isoformat(),"strategy_total_return":float(eq.iloc[-1]-1),"gross_strategy_total_return":float(geq.iloc[-1]-1),"strategy_cagr":cagr(eq),"benchmark_total_return":float(spyeq.iloc[-1]-1),"benchmark_cagr":cagr(spyeq),"max_drawdown":max_drawdown(eq),"benchmark_max_drawdown":max_drawdown(spyeq),"sharpe":sharpe(net),"benchmark_sharpe":sharpe(spyret),"sortino":sortino(net),"annualized_volatility":annualized_volatility(net),"total_turnover":float(turn.sum()),"estimated_cost_drag_return_points":float((geq.iloc[-1]-1)-(eq.iloc[-1]-1)),"time_in_market":float((exposure>0).mean()),"average_gross_exposure":float(exposure.mean()),"spy_fallback":spy_fallback,"fallback_time":float((fallback_exposure>0).mean()),"fallback_days":fallback_days,"entry_score":float(cfg.entry_score),"min_hold_trading_days":min_hold_trading_days,"max_sectors":maxs,"weighting":weighting,**stats}
    return {"summary":summary,"equity":pd.DataFrame({"strategy":eq,"strategy_gross":geq,"spy":spyeq}),"weights":wh,"turnover":turn,"trades":trades,"sector_contribution":[],"regime_breakdown":[],"best_trades":[] if trades.empty else trades.nlargest(5,"return").to_dict("records"),"worst_trades":[] if trades.empty else trades.nsmallest(5,"return").to_dict("records")}
