import numpy as np

def cagr(e):
    years=(e.index[-1]-e.index[0]).days/365.25
    return float((e.iloc[-1]/e.iloc[0])**(1/years)-1) if years>0 else 0.0

def max_drawdown(e): return float((e/e.cummax()-1).min())
def sharpe(r):
    r=r.dropna(); s=r.std(ddof=0)
    return float(np.sqrt(252)*r.mean()/s) if s else 0.0
def sortino(r):
    r=r.dropna(); d=r[r<0]; s=d.std(ddof=0)
    return float(np.sqrt(252)*r.mean()/s) if len(d)>1 and s else 0.0
def annualized_volatility(r): return float(r.dropna().std(ddof=0)*np.sqrt(252))
