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

### Strategy catalogue comparison

The separate `paperswithbacktest/awesome-systematic-trading` catalogue includes
`static/strategies/sector-momentum-rotational-system.py`, which buys the three
strongest sectors by roughly 12-month return and rebalances monthly. To compare
its idea with ALPHABOT's weak-sector recovery rule, run:

```bash
python -m scripts.compare_catalogue --start 2015-01-01 --end 2025-01-01
```

This **research-only** challenger uses ALPHABOT's 11 sector ETFs, two positions
capped at 50% each, a 252-trading-day lookback, and the same 10-basis-point
turnover cost as the baseline. The source uses ten ETFs (including VNQ) and
three positions, so this is an adaptation rather than a reproduction. Decisions
use the previous completed close and start earning returns on the next bar.
The command prints both strategies and SPY for the same evaluation dates,
plus turnover and days invested. It does not place orders or change the
scheduled paper strategy. Treat historical results as a screening step: repeat
across separate market periods and check the paper journal before changing
execution. Data downloads may fail or be rate limited; a failed download
produces no comparison.

The separate shadow scanner shows what both strategies currently favor:

```bash
python -m scripts.shadow_scan
```

Its GitHub Actions workflow runs after the U.S. market close on weekdays and
uploads a JSON report when market data is available. It requires no broker
credentials and has no order access. The selector explicitly reports
`unvalidated` until we have forward observations and a tested selection rule;
the automatic paper executor continues using the locked rotation strategy.

Run the selector research on the same historical sector bars:

```bash
python -m scripts.research_selector --start 2015-01-01 --end 2025-01-01
```

It waits for a full 252-session record after *both* strategies first hold a
position. On the first trading day of each subsequent quarter, it selects the
strategy with the better positive trailing Sharpe and positive trailing total
return. If neither qualifies it holds cash. It uses only earlier sessions to
make each decision, applies the chosen strategy's next-bar target weights,
and charges turnover cost to the combined portfolio, including switches. The
JSON output includes the dated decisions and compares both standalone
strategies, the selected portfolio, and SPY over the same evaluation window.
This is a fixed research rule, not a validated forecast or a live/paper trading
switch. The existing automatic paper executor does not read its output.

The catalogue's 60 code examples span sector ETFs, other asset classes,
individual stocks, futures, currency and crypto. The next compatible research
candidate is the asset-class trend-following idea (ten-month moving average),
but its original SPY/EFA/IEF/VNQ/GSG universe requires a separate comparison.
Strategies needing short positions, leverage, proprietary fundamentals, or
different brokerage data cannot be safely plugged into this sector-only
paper account without their own data and risk design.

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
Use a dedicated Alpaca paper account containing only this strategy's sector
positions. Unexpected holdings or a broker order history too large to verify
stop execution.

The dashboard and manual paper endpoints remain available behind the configured
dashboard login. The scheduled job calls the broker directly and needs no
dashboard credentials. No code path points to Alpaca's live-money trading API.
