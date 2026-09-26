"""Scheduled, paper-only weekly rebalance with broker-backed order deduplication."""

from datetime import datetime
from zoneinfo import ZoneInfo

from src.broker import alpaca
from src.config import SECTOR_ETFS
from src.paper_executor import _journal, build_plan

ACTIVE_ORDER_STATES = {"new", "accepted", "pending_new", "partially_filled", "accepted_for_bidding"}
SUCCESS_ORDER_STATES = ACTIVE_ORDER_STATES | {"filled"}


def run_automatic_paper() -> dict:
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return {"status": "skipped", "reason": "weekend"}
    if not alpaca.clock().get("is_open"):
        return {"status": "skipped", "reason": "market_closed"}

    week = now.strftime("%G%V")
    prefix = f"alphabot-{week}-"
    prior = alpaca.orders(status="all", limit=500)
    own = {o.get("symbol"): o for o in prior if str(o.get("client_order_id") or "").startswith(prefix)}
    bad = [o for o in own.values() if o.get("status") not in SUCCESS_ORDER_STATES]
    if bad:
        raise RuntimeError("A weekly paper order was rejected or canceled; review the broker before retrying")
    if any(o.get("status") in ACTIVE_ORDER_STATES for o in own.values()):
        return {"status": "waiting", "reason": "weekly_order_pending"}
    if any(o.get("symbol") in SECTOR_ETFS and o.get("status") in ACTIVE_ORDER_STATES
           for o in prior if not str(o.get("client_order_id") or "").startswith(prefix)):
        raise RuntimeError("Another open sector order exists in the paper account")

    plan = build_plan()
    if plan["regime"] == "UNKNOWN":
        raise RuntimeError("Market regime is unknown; no paper orders submitted")
    actions = [a for a in plan["actions"] if a["action"] in {"SELL", "CLOSE", "BUY"}
               and a["symbol"] not in own]
    # Let sells fill before planning buys against the updated cash balance.
    sells = [a for a in actions if a["action"] in {"SELL", "CLOSE"}]
    batch = sells if sells else [a for a in actions if a["action"] == "BUY"]
    positions = {p["symbol"]: p for p in alpaca.positions()}
    submitted = []
    for action in batch:
        symbol = action["symbol"]
        client_id = prefix + symbol.lower()
        if action["action"] == "CLOSE":
            position = positions.get(symbol)
            if not position or float(position.get("qty") or 0) <= 0:
                raise RuntimeError(f"Expected long paper position missing for {symbol}")
            order = alpaca.submit_qty_order(symbol, str(position["qty"]), "sell", client_id)
        else:
            order = alpaca.submit_market_order(
                symbol, float(action["notional"]), action["action"].lower(), client_id
            )
        submitted.append({"symbol": symbol, "action": action["action"], "order_id": order.get("id")})

    result = {"status": "submitted" if submitted else "no_action", "week": week,
              "phase": "sells" if sells else "buys", "orders": submitted,
              "signal_date": plan["created_at"]}
    _journal("AUTO_RUN", result)
    return result
