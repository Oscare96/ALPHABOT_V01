# ALPHABOT_V01

Research-first sector rotation swing trading bot.

## Core idea

Do not buy a sector simply because it is down. Find sectors that were weak, then wait for stabilization, improving relative strength, and rotation confirmation before entry. Sell progressively as strength becomes extended or the rotation thesis deteriorates.

## V0.1

- SPY + 11 U.S. sector ETFs
- Daily market data
- Rotation score (0-100)
- Sector states
- Market regime filter
- Weekly portfolio rebalance
- Transaction-cost assumptions
- Historical backtester
- FastAPI endpoints
- Railway deployment config

## Run

```bash
pip install -r requirements.txt
uvicorn src.main:app --reload
```

API docs: `/docs`

Scan: `GET /api/scan`

Backtest: `GET /api/backtest?start=2010-01-01`

CLI:

```bash
python -m scripts.scan
python -m scripts.backtest --start 2010-01-01
```

## Deployment

Connect this repository to Railway. `railway.json` and `Procfile` contain the start configuration.

## Safety boundary

V0.1 is research/backtesting only. It does not contain live brokerage credentials or live-money execution. Paper trading comes after out-of-sample and walk-forward testing.
