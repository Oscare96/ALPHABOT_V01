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

Before opening the dashboard or API, set `ALPHABOT_DASHBOARD_USER` and
`ALPHABOT_DASHBOARD_PASSWORD` to private values. Your browser will ask for
these credentials. Without both values, the dashboard and trading endpoints
return 503 and no paper orders can be submitted. `/health` remains public for
Railway's health check. Set the same variables in Railway before deploying.

Scan: `GET /api/scan`

Backtest: `GET /api/backtest?start=2010-01-01`

CLI:

```bash
python -m scripts.scan
python -m scripts.backtest --start 2010-01-01
python -m scripts.backtest --start 2010-01-01 --paper-rules
```

`--paper-rules` tests the locked paper settings: entry score 58, up to two
sectors, 30 trading day minimum hold, and a 50% cap per sector. It still uses
historical daily bars and estimated trading costs, so compare its signals
and execution timing against the actual paper journal before drawing conclusions.

## Deployment

Connect this repository to Railway. `railway.json` and `Procfile` contain the start configuration.

## Automatic paper trading

The workflow at `.github/workflows/paper-rebalance.yml` tries three times each
US weekday during market hours. It uses the locked 58-point, top-two-sector
paper strategy. The first run in a week may sell; a later run buys after the
sells fill. Broker client order IDs prevent the same sector from receiving a
second order that week. Failed data downloads, stale bars, account blocks, and
unexpected open sector orders stop the run. Check GitHub Actions failures and
the Alpaca paper account regularly; this is automated execution, not a promise
that every scheduled run will arrive or fill.

Before enabling it on the default branch, set repository Actions secrets
`ALPACA_PAPER_KEY_ID` and `ALPACA_PAPER_SECRET_KEY` to **paper-only** keys. Do not
put them in code or chat. Run the workflow manually once during market hours
and compare the resulting paper positions and order IDs with the plan.

The dashboard and manual paper endpoints remain available behind the configured
dashboard login. The scheduled job calls the broker directly and needs no
dashboard credentials. No code path points to Alpaca's live-money trading API.
