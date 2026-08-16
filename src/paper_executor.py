import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dataclasses import replace

from src.config import DEFAULT_CONFIG, SECTOR_ETFS
from src.data.market_data import download_market_data
from src.strategy.rotation import latest_scan
from src.broker import alpaca

LOCKED_CONFIG = replace(DEFAULT_CONFIG, entry_score=58.0)
MAX_SECTORS = 2
MIN_HOLD_TRADING_DAYS = 30
MAX_POSITION_PCT = 0.50
MIN_ORDER_NOTIONAL = 25.0
RISK_OFF_GROSS = float(DEFAULT_CONFIG.risk_off_size_multiplier)
JOURNAL_PATH = Path(os.getenv("FORWARD_JOURNAL_PATH", "/tmp/alphabot_forward_journal.jsonl"))
_latest_plan: dict | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _journal(event: str, payload: dict) -> None:
    try:
        JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        row = {"timestamp": _now_iso(), "event": event, **payload}
        with JOURNAL_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception:
        pass


def journal(limit: int = 100) -> list[dict]:
    if not JOURNAL_PATH.exists():
        return []
    rows = []
    try:
        with JOURNAL_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return rows[-max(1, min(limit, 500)):][::-1]


def _position_age_trading_days(symbol: str, orders: list[dict], trading_index) -> int | None:
    buys = [
        o for o in orders
        if o.get("symbol") == symbol and o.get("side") == "buy" and o.get("status") == "filled" and o.get("filled_at")
    ]
    if not buys:
        return None
    latest = max(buys, key=lambda o: o.get("filled_at", ""))
    try:
        filled = datetime.fromisoformat(str(latest["filled_at"]).replace("Z", "+00:00")).date()
        return sum(1 for d in trading_index if d.date() > filled)
    except Exception:
        return None


def build_plan() -> dict:
    global _latest_plan

    account = alpaca.account()
    positions = alpaca.positions()
    orders = alpaca.orders(status="all", limit=100)
    market = download_market_data(start="2023-01-01")
    scan = latest_scan(market, LOCKED_CONFIG)
    rows = scan.to_dict("records")
    by_symbol = {r["symbol"]: r for r in rows}
    trading_index = market["SPY"].index

    equity = float(account.get("equity") or 0.0)
    if equity <= 0:
        raise RuntimeError("Paper account equity must be positive")

    sector_positions = {p["symbol"]: p for p in positions if p.get("symbol") in SECTOR_ETFS}
    held = set(sector_positions)
    protected = set()
    ages = {}
    for symbol in held:
        age = _position_age_trading_days(symbol, orders, trading_index)
        ages[symbol] = age
        if age is None or age < MIN_HOLD_TRADING_DAYS:
            protected.add(symbol)

    normal_hold = {
        s for s in held - protected
        if s in by_symbol and float(by_symbol[s].get("rotation_score") or 0) >= float(LOCKED_CONFIG.hold_score)
    }

    eligible = [r for r in rows if bool(r.get("eligible")) and r.get("symbol") not in held]
    eligible.sort(key=lambda r: float(r.get("rotation_score") or 0), reverse=True)

    retained = sorted(protected | normal_hold, key=lambda s: float(by_symbol.get(s, {}).get("rotation_score") or 0), reverse=True)
    selected = retained[:MAX_SECTORS]
    for r in eligible:
        if len(selected) >= MAX_SECTORS:
            break
        if r["symbol"] not in selected:
            selected.append(r["symbol"])

    regime = rows[0].get("market_regime") if rows else "UNKNOWN"
    if regime == "RISK_OFF":
        per_symbol_pct = (RISK_OFF_GROSS / len(selected)) if selected else 0.0
    else:
        per_symbol_pct = MAX_POSITION_PCT

    target_values = {s: equity * per_symbol_pct for s in selected}
    actions = []

    for symbol, p in sector_positions.items():
        current_value = abs(float(p.get("market_value") or 0.0))
        if symbol not in selected:
            if symbol in protected:
                actions.append({"symbol": symbol, "action": "HOLD", "reason": "minimum_hold_protected", "age_trading_days": ages.get(symbol), "current_value": current_value})
            else:
                actions.append({"symbol": symbol, "action": "CLOSE", "reason": "no_longer_selected", "age_trading_days": ages.get(symbol), "current_value": current_value})
            continue

        target = target_values[symbol]
        delta = target - current_value
        if abs(delta) < MIN_ORDER_NOTIONAL:
            actions.append({"symbol": symbol, "action": "HOLD", "reason": "within_rebalance_band", "current_value": current_value, "target_value": target})
        elif delta > 0:
            actions.append({"symbol": symbol, "action": "BUY", "notional": round(delta, 2), "reason": "rebalance_to_target", "current_value": current_value, "target_value": target})
        else:
            actions.append({"symbol": symbol, "action": "SELL", "notional": round(abs(delta), 2), "reason": "rebalance_to_target", "current_value": current_value, "target_value": target})

    for symbol in selected:
        if symbol not in sector_positions:
            target = target_values[symbol]
            if target >= MIN_ORDER_NOTIONAL:
                actions.append({"symbol": symbol, "action": "BUY", "notional": round(target, 2), "reason": "new_locked_signal", "current_value": 0.0, "target_value": target})

    executable = [a for a in actions if a["action"] in {"BUY", "SELL", "CLOSE"}]
    core = {
        "created_at": _now_iso(),
        "paper_only": True,
        "strategy_locked": True,
        "equity": equity,
        "regime": regime,
        "selected": selected,
        "rules": {
            "entry_threshold": 58,
            "hold_score": float(LOCKED_CONFIG.hold_score),
            "min_hold_trading_days": MIN_HOLD_TRADING_DAYS,
            "max_sectors": MAX_SECTORS,
            "max_position_pct": MAX_POSITION_PCT,
            "risk_off_gross": RISK_OFF_GROSS,
            "weekly_evaluation": True,
            "fallback": "cash",
        },
        "actions": actions,
        "executable_actions": len(executable),
    }
    plan_id = hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:20]
    plan = {"plan_id": plan_id, **core}
    _latest_plan = plan
    _journal("PLAN", plan)
    return plan


def execute_plan(plan_id: str) -> dict:
    global _latest_plan
    if not _latest_plan or _latest_plan.get("plan_id") != plan_id:
        raise RuntimeError("Plan is missing or stale. Preview a fresh plan before execution.")

    clock = alpaca.clock()
    if not bool(clock.get("is_open")):
        raise RuntimeError("Alpaca reports the market is closed. Paper orders were not submitted.")

    results = []
    actions = [a for a in _latest_plan["actions"] if a["action"] in {"BUY", "SELL", "CLOSE"}]
    # Reduce/close first, then add exposure.
    actions.sort(key=lambda a: 1 if a["action"] == "BUY" else 0)
    for i, action in enumerate(actions):
        symbol = action["symbol"]
        try:
            if action["action"] == "CLOSE":
                order = alpaca.close_position(symbol)
            else:
                client_id = f"alphabot-{plan_id[:10]}-{i}-{symbol.lower()}"
                order = alpaca.submit_market_order(symbol, float(action["notional"]), action["action"].lower(), client_id)
            results.append({"symbol": symbol, "action": action["action"], "submitted": True, "order_id": order.get("id"), "status": order.get("status")})
        except Exception as e:
            results.append({"symbol": symbol, "action": action["action"], "submitted": False, "error": str(e)[:240]})

    payload = {"plan_id": plan_id, "paper_only": True, "submitted_at": _now_iso(), "results": results}
    _journal("EXECUTION", payload)
    _latest_plan = None
    return payload
