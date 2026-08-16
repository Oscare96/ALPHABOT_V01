from dataclasses import replace

import numpy as np
import pandas as pd

from src.config import BENCHMARK, DEFAULT_CONFIG, SECTOR_ETFS
from src.strategy.rotation import build_features
from src.backtest.metrics import cagr, max_drawdown, sharpe, sortino, annualized_volatility


def _rebalance_mask(index, rebalance_weeks=1):
    if rebalance_weeks < 1: raise ValueError("rebalance_weeks must be >= 1")
    iso=index.isocalendar(); keys=pd.Series(list(zip(iso.year,iso.week)),index=index); weekly_first=~keys.duplicated(); weekly_dates=index[weekly_first]; selected=set(weekly_dates[::rebalance_weeks]); return pd.Series(index.isin(selected),index=index)

def _build_trade_ledger(effective_weights,prices,features):
    trades=[]
    for symbol in effective_weights.columns:
        held=effective_weights[symbol]>0; starts=held & ~held.shift(1,fill_value=False); ends=~held & held.shift(1,fill_value=False); start_dates=list(held.index[starts]); end_dates=list(held.index[ends])
        if held.iloc[-1]: end_dates.append(held.index[-1])
        for entry_date in start_dates:
            exits_after=[d for d in end_dates if d>=entry_date]
            if not exits_after: continue
            exit_date=exits_after[0]; exit_loc=prices.index.get_loc(exit_date); price_exit_date=prices.index[max(0,exit_loc-1)] if not held.loc[exit_date] else exit_date; entry_price=float(prices.loc[entry_date,symbol]); exit_price=float(prices.loc[price_exit_date,symbol]); trade_return=exit_price/entry_price-1.0 if entry_price else 0.0; holding_days=int((price_exit_date-entry_date).days)
            try:
                row=features.loc[entry_date]; row=row.to_frame().T if isinstance(row,pd.Series) else row; f=row[row["symbol"]==symbol].iloc[0]; entry_score=float(f["rotation_score"]); regime=str(f["market_regime"]); state=str(f["state"])
            except Exception: entry_score,regime,state=None,"UNKNOWN","UNKNOWN"
            trades.append({"symbol":symbol,"sector":SECTOR_ETFS[symbol],"entry_date":entry_date.date().isoformat(),"exit_date":price_exit_date.date().isoformat(),"entry_price":entry_price,"exit_price":exit_price,"return":float(trade_return),"holding_days":holding_days,"entry_score":entry_score,"entry_regime":regime,"entry_state":state})
    return pd.DataFrame(trades)

def _trade_stats(trades):
    if trades.empty: return {"number_of_trades":0,"win_rate":0.0,"profit_factor":0.0,"average_trade_return":0.0,"average_winner":0.0,"average_loser":0.0,"average_holding_days":0.0}
    wins=trades[trades["return"]>0]["return"]; losses=trades[trades["return"]<0]["return"]; gp=float(wins.sum()); gl=abs(float(losses.sum())); pf=gp/gl if gl>0 else (999.0 if gp>0 else 0.0)
    return {"number_of_trades":int(len(trades)),"win_rate":float((trades["return"]>0).mean()),"profit_factor":float(pf),"average_trade_return":float(trades["return"].mean()),"average_winner":float(wins.mean()) if len(wins) else 0.0,"average_loser":float(losses.mean()) if len(losses) else 0.0,"average_holding_days":float(trades["holding_days"].mean())}

def _compound_return(r):
    c=r.dropna(); return 0.0 if c.empty else float((1.0+c).prod()-1.0)

def _force_exit_for_regime(regime,policy):
    if policy is None:return False
    if policy=="NON_RISK_ON":return regime!="RISK_ON"
    if policy=="RISK_OFF":return regime=="RISK_OFF"
    raise ValueError(f"Unknown exit_policy: {policy}")

def _target_weights(symbols, gross, returns, dt, weighting):
    if not symbols: return pd.Series(dtype=float)
    if weighting=="equal": return pd.Series(gross/len(symbols),index=symbols)
    if weighting=="inverse_vol":
        hist=returns.loc[:dt,symbols].tail(20); vol=hist.std().replace(0,np.nan); inv=(1.0/vol).replace([np.inf,-np.inf],np.nan).dropna()
        if len(inv)!=len(symbols) or inv.sum()<=0:return pd.Series(gross/len(symbols),index=symbols)
        return gross*inv/inv.sum()
    raise ValueError(f"Unknown weighting: {weighting}")

def run_backtest(data,config=DEFAULT_CONFIG,entry_regime=None,exit_policy=None,entry_score_override=None,rebalance_weeks=1,min_hold_trading_days=0,max_sectors_override=None,weighting="equal"):
    effective_config=replace(config,entry_score=float(entry_score_override)) if entry_score_override is not None else config; max_sectors=int(max_sectors_override or effective_config.max_sectors)
    features=build_features(data,effective_config); prices=pd.DataFrame({s:data[s]["close"] for s in SECTOR_ETFS}).sort_index(); spy=data[BENCHMARK]["close"].reindex(prices.index).ffill(); returns=prices.pct_change(fill_method=None).fillna(0.0); spy_returns=spy.pct_change(fill_method=None).fillna(0.0); equal_sector_returns=returns.mean(axis=1); dates=prices.index; rebalance_mask=_rebalance_mask(dates,rebalance_weeks)
    current=pd.Series(0.0,index=prices.columns); weight_history=pd.DataFrame(0.0,index=dates,columns=prices.columns); turnover=pd.Series(0.0,index=dates); rebalance_count=0; forced_exit_events=0; entry_loc={}
    for loc,dt in enumerate(dates):
        if rebalance_mask.loc[dt]:
            try: day=features.loc[dt].copy()
            except KeyError: weight_history.loc[dt]=current; continue
            if isinstance(day,pd.Series):day=day.to_frame().T
            day=day.dropna(subset=["rotation_score","symbol"])
            if day.empty:weight_history.loc[dt]=current;continue
            regime=str(day.iloc[0]["market_regime"]); held=set(current[current>0].index); force=_force_exit_for_regime(regime,exit_policy); protected={s for s in held if min_hold_trading_days>0 and (loc-entry_loc.get(s,loc))<min_hold_trading_days}
            if force and held: holdable=day.iloc[0:0].copy();protected=set();forced_exit_events+=1
            else:
                normal=day[day["symbol"].isin(held)&(day["rotation_score"]>=effective_config.hold_score)]; protected_hold=day[day["symbol"].isin(protected)]; holdable=pd.concat([normal,protected_hold],ignore_index=True).drop_duplicates("symbol")
            entrants=day[day["eligible"]&(~day["symbol"].isin(held))]
            if entry_regime is not None:entrants=entrants[entrants["market_regime"]==entry_regime]
            entrants=entrants.sort_values("rotation_score",ascending=False); pool=pd.concat([holdable,entrants],ignore_index=True).sort_values("rotation_score",ascending=False).drop_duplicates("symbol").head(max_sectors); target=pd.Series(0.0,index=prices.columns)
            if len(pool):
                gross=effective_config.risk_off_size_multiplier if regime=="RISK_OFF" else 1.0; syms=pool["symbol"].tolist(); target.loc[syms]=_target_weights(syms,gross,returns,dt,weighting)
            new=set(target[target>0].index)-held; exited=held-set(target[target>0].index)
            for s in new:entry_loc[s]=loc
            for s in exited:entry_loc.pop(s,None)
            turnover.loc[dt]=float((target-current).abs().sum());current=target;rebalance_count+=1
        weight_history.loc[dt]=current
    effective_weights=weight_history.shift(1).fillna(0.0); gross_returns=(effective_weights*returns).sum(axis=1); costs=turnover*(effective_config.trading_cost_bps/10000.0); strategy_returns=gross_returns-costs; gross_equity=(1+gross_returns).cumprod(); equity=(1+strategy_returns).cumprod(); spy_equity=(1+spy_returns).cumprod(); equal_equity=(1+equal_sector_returns).cumprod(); exposure=effective_weights.sum(axis=1); invested=exposure>0; trades=_build_trade_ledger(effective_weights,prices,features); trade_stats=_trade_stats(trades); contributions=(effective_weights*returns).sum(axis=0).sort_values(ascending=False); sector_contribution=[{"symbol":s,"sector":SECTOR_ETFS[s],"return_contribution":float(v)} for s,v in contributions.items()]; feature_regime=features.groupby(level=0)["market_regime"].first().reindex(dates).ffill(); regime_returns=[]
    for regime in ["RISK_ON","NEUTRAL","RISK_OFF"]:
        mask=feature_regime==regime
        if mask.any():regime_returns.append({"regime":regime,"days":int(mask.sum()),"strategy_return_sum":float(strategy_returns.loc[mask].sum()),"strategy_compounded_return":_compound_return(strategy_returns.loc[mask]),"gross_compounded_return":_compound_return(gross_returns.loc[mask]),"average_daily_return":float(strategy_returns.loc[mask].mean()),"average_exposure":float(exposure.loc[mask].mean())})
    best=[] if trades.empty else trades.nlargest(5,"return").to_dict(orient="records");worst=[] if trades.empty else trades.nsmallest(5,"return").to_dict(orient="records");gross_total=float(gross_equity.iloc[-1]-1);net_total=float(equity.iloc[-1]-1)
    summary={"start":equity.index.min().date().isoformat(),"end":equity.index.max().date().isoformat(),"entry_score":float(effective_config.entry_score),"rebalance_weeks":int(rebalance_weeks),"min_hold_trading_days":int(min_hold_trading_days),"max_sectors":max_sectors,"weighting":weighting,"entry_regime_filter":entry_regime or "ALL","exit_policy":exit_policy or "STANDARD","forced_exit_events":int(forced_exit_events),"strategy_total_return":net_total,"gross_strategy_total_return":gross_total,"estimated_cost_drag_return_points":float(gross_total-net_total),"estimated_cost_sum":float(costs.sum()),"total_turnover":float(turnover.sum()),"benchmark_total_return":float(spy_equity.iloc[-1]-1),"equal_sector_total_return":float(equal_equity.iloc[-1]-1),"strategy_cagr":cagr(equity),"gross_strategy_cagr":cagr(gross_equity),"benchmark_cagr":cagr(spy_equity),"max_drawdown":max_drawdown(equity),"benchmark_max_drawdown":max_drawdown(spy_equity),"sharpe":sharpe(strategy_returns),"benchmark_sharpe":sharpe(spy_returns),"sortino":sortino(strategy_returns),"annualized_volatility":annualized_volatility(strategy_returns),"average_turnover":float(turnover.mean()),"number_of_rebalances":int(rebalance_count),"average_gross_exposure":float(exposure.mean()),"time_in_market":float(invested.mean()),"cash_time":float((~invested).mean()),**trade_stats}
    return {"summary":summary,"equity":pd.DataFrame({"strategy":equity,"strategy_gross":gross_equity,"spy":spy_equity,"equal_sectors":equal_equity}),"weights":weight_history,"turnover":turnover,"trades":trades,"sector_contribution":sector_contribution,"regime_breakdown":regime_returns,"best_trades":best,"worst_trades":worst}
