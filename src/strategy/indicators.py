import numpy as np
import pandas as pd

def rsi(close, period=14):
    delta = close.diff(); gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - 100/(1+rs)).fillna(50.0)

def atr(df, period=14):
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"]-df["low"], (df["high"]-prev).abs(), (df["low"]-prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()

def rolling_drawdown(close, window=60):
    return close / close.rolling(window, min_periods=20).max() - 1

def linear_slope(series, window=10):
    def calc(v):
        v=np.asarray(v,dtype=float)
        if np.isnan(v).any(): return np.nan
        x=np.arange(len(v),dtype=float); x-=x.mean(); y=v-v.mean(); d=np.square(x).sum()
        return float((x*y).sum()/d) if d else 0.0
    return series.rolling(window,min_periods=window).apply(calc,raw=True)
