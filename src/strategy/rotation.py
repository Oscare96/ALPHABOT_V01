import numpy as np
import pandas as pd
from src.config import BENCHMARK, DEFAULT_CONFIG, SECTOR_ETFS
from src.strategy.indicators import rsi, atr, rolling_drawdown, linear_slope

def clip01(s): return s.clip(0,1)

def build_features(data, config=DEFAULT_CONFIG):
    spy=data[BENCHMARK]["close"]; spy200=spy.rolling(200).mean(); frames=[]
    for symbol,name in SECTOR_ETFS.items():
        df=data[symbol]; c=df["close"]; f=pd.DataFrame(index=df.index)
        f["symbol"]=symbol; f["sector"]=name; f["close"]=c
        f["ret_5d"]=c.pct_change(5); f["ret_20d"]=c.pct_change(20); f["ret_60d"]=c.pct_change(60)
        f["ma20"]=c.rolling(20).mean(); f["ma50"]=c.rolling(50).mean(); f["ma200"]=c.rolling(200).mean()
        f["above_20dma"]=c>f.ma20; f["above_50dma"]=c>f.ma50; f["above_200dma"]=c>f.ma200
        f["rsi_14"]=rsi(c); f["atr_pct"]=atr(df)/c; f["drawdown_60d"]=rolling_drawdown(c)
        sp=spy.reindex(f.index).ffill(); rs=c/sp
        f["rs_20d"]=rs.pct_change(20); f["rs_slope_10d"]=linear_slope(rs.pct_change().rolling(5).mean(),10)
        vol=df["volume"].astype(float); f["volume_ratio"]=vol/vol.rolling(20).mean().replace(0,np.nan)
        low10=df["low"].rolling(10).min(); f["new_low_pressure"]=(low10<low10.shift(5)).astype(float)
        f["higher_close_3"]=((c>c.shift(1))&(c.shift(1)>=c.shift(2))).astype(float)
        f["spy_above_200dma"]=sp>spy200.reindex(f.index).ffill(); f["spy_ret_20d"]=sp.pct_change(20)
        frames.append(f)
    a=pd.concat(frames).sort_index()
    a["weak_rank"]=a.groupby(level=0).ret_20d.rank(ascending=True,method="min")
    weakness=clip01((-a.ret_20d-.02)/.13)-.7*clip01((-a.ret_20d-.20)/.15); weakness=clip01(weakness)
    stabilization=.55*(1-a.new_low_pressure)+.45*clip01((a.rsi_14-32)/18)
    rs20=clip01((a.rs_20d+.03)/.08); rsrank=a.groupby(level=0).rs_slope_10d.rank(pct=True)
    relative=.55*rs20+.45*rsrank
    momentum=.6*clip01((a.ret_5d+.02)/.06)+.4*a.higher_close_3
    trend=.55*a.above_20dma.astype(float)+.30*a.above_50dma.astype(float)+.15*a.above_200dma.astype(float)
    volume=clip01((a.volume_ratio-.8)/.7)
    a["rotation_score"]=(15*weakness+20*stabilization+25*relative+15*momentum+15*trend+10*volume)
    a["candidate"]=a.weak_rank<=config.weak_sector_rank_max
    a["eligible"]=a.candidate&(a.rotation_score>=config.entry_score)
    a["market_regime"]=np.select([a.spy_above_200dma&(a.spy_ret_20d>0),a.spy_above_200dma],["RISK_ON","NEUTRAL"],default="RISK_OFF")
    a["state"]=np.select([(a.rotation_score>=80)&a.above_20dma&(a.rs_20d>.02),(a.rotation_score>=config.entry_score)&a.above_20dma,(a.rotation_score>=55)&(~a.above_20dma),(a.ret_20d<=-.08)&(a.rsi_14<=35),a.ret_20d<0,(a.ret_20d>=.10)&(a.rsi_14>=70)],["EXPANSION","ROTATING","ACCUMULATION","OVERSOLD","DECLINING","OVEREXTENDED"],default="NEUTRAL")
    return a

def latest_scan(data,config=DEFAULT_CONFIG):
    f=build_features(data,config).dropna(subset=["rotation_score"]); dt=f.index.max(); x=f.loc[dt].copy()
    if isinstance(x,pd.Series): x=x.to_frame().T
    cols=["symbol","sector","state","rotation_score","ret_20d","ret_60d","rsi_14","rs_20d","rs_slope_10d","drawdown_60d","above_20dma","above_50dma","market_regime","eligible","weak_rank"]
    x=x[cols].sort_values("rotation_score",ascending=False); x.insert(0,"date",pd.Timestamp(dt).date().isoformat())
    return x.reset_index(drop=True)
