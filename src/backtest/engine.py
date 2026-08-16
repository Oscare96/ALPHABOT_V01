import pandas as pd
from src.config import BENCHMARK,DEFAULT_CONFIG,SECTOR_ETFS
from src.strategy.rotation import build_features
from src.backtest.metrics import cagr,max_drawdown,sharpe,sortino,annualized_volatility

def run_backtest(data,config=DEFAULT_CONFIG):
    f=build_features(data,config); prices=pd.DataFrame({s:data[s]["close"] for s in SECTOR_ETFS}).sort_index(); spy=data[BENCHMARK]["close"].reindex(prices.index).ffill()
    returns=prices.pct_change().fillna(0); spyret=spy.pct_change().fillna(0); dates=prices.index
    weeks=pd.Series(list(zip(dates.isocalendar().year,dates.isocalendar().week)),index=dates); rebalance=~weeks.duplicated()
    current=pd.Series(0.0,index=prices.columns); wh=pd.DataFrame(0.0,index=dates,columns=prices.columns); turnover=pd.Series(0.0,index=dates); count=0
    for dt in dates:
        if rebalance.loc[dt]:
            try: day=f.loc[dt].copy()
            except KeyError: wh.loc[dt]=current; continue
            if isinstance(day,pd.Series): day=day.to_frame().T
            day=day.dropna(subset=["rotation_score","symbol"]); held=set(current[current>0].index)
            hold=day[day.symbol.isin(held)&(day.rotation_score>=config.hold_score)]
            enter=day[day.eligible&(~day.symbol.isin(held))].sort_values("rotation_score",ascending=False)
            pool=pd.concat([hold,enter],ignore_index=True).sort_values("rotation_score",ascending=False).drop_duplicates("symbol").head(config.max_sectors)
            target=pd.Series(0.0,index=prices.columns)
            if len(pool):
                gross=config.risk_off_size_multiplier if str(pool.iloc[0].market_regime)=="RISK_OFF" else 1.0
                target.loc[pool.symbol.tolist()]=gross/len(pool)
            turnover.loc[dt]=float((target-current).abs().sum()); current=target; count+=1
        wh.loc[dt]=current
    effective=wh.shift(1).fillna(0); gross=(effective*returns).sum(axis=1); strategy=gross-turnover*(config.trading_cost_bps/10000)
    eq=(1+strategy).cumprod(); beq=(1+spyret).cumprod()
    summary={"start":eq.index.min().date().isoformat(),"end":eq.index.max().date().isoformat(),"strategy_total_return":float(eq.iloc[-1]-1),"benchmark_total_return":float(beq.iloc[-1]-1),"strategy_cagr":cagr(eq),"benchmark_cagr":cagr(beq),"max_drawdown":max_drawdown(eq),"sharpe":sharpe(strategy),"sortino":sortino(strategy),"annualized_volatility":annualized_volatility(strategy),"average_turnover":float(turnover.mean()),"number_of_rebalances":count}
    return {"summary":summary,"equity":pd.DataFrame({"strategy":eq,"spy":beq}),"weights":wh,"turnover":turnover}
