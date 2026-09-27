from datetime import datetime

import pytest

from src import auto_paper


class Monday(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 28, 11, 23, tzinfo=tz)


def setup_run(monkeypatch, actions, prior=None, positions=None):
    monkeypatch.setattr(auto_paper, "datetime", Monday)
    monkeypatch.setattr(auto_paper.alpaca, "clock", lambda: {"is_open": True})
    monkeypatch.setattr(auto_paper.alpaca, "orders", lambda **_: prior or [])
    monkeypatch.setattr(auto_paper.alpaca, "positions", lambda: positions or [])
    monkeypatch.setattr(auto_paper, "build_plan", lambda: {
        "regime": "RISK_ON", "actions": actions, "created_at": "2026-09-28T15:23:00+00:00"
    })
    monkeypatch.setattr(auto_paper, "_journal", lambda *_: None)


def test_sells_before_buying_and_uses_stable_order_id(monkeypatch):
    setup_run(monkeypatch, [
        {"symbol": "XLK", "action": "CLOSE"},
        {"symbol": "XLE", "action": "BUY", "notional": 500.0},
    ], positions=[{"symbol": "XLK", "qty": "1.25"}])
    sent = []
    monkeypatch.setattr(auto_paper.alpaca, "submit_qty_order", lambda *args: sent.append(args) or {"id": "one"})
    monkeypatch.setattr(auto_paper.alpaca, "submit_market_order", lambda *args: pytest.fail("Buy ran before sell fill"))
    result = auto_paper.run_automatic_paper()
    assert result["phase"] == "sells"
    assert sent == [("XLK", "1.25", "sell", "alphabot-202640-xlk")]


def test_repeated_week_skips_already_submitted_symbol(monkeypatch):
    setup_run(monkeypatch, [{"symbol": "XLK", "action": "BUY", "notional": 500.0}],
              prior=[{"symbol": "XLK", "client_order_id": "alphabot-202640-xlk", "status": "filled"}])
    monkeypatch.setattr(auto_paper.alpaca, "submit_market_order", lambda *args: pytest.fail("Duplicate order"))
    assert auto_paper.run_automatic_paper()["status"] == "no_action"


def test_pending_weekly_order_waits(monkeypatch):
    setup_run(monkeypatch, [], prior=[{
        "symbol": "XLK", "client_order_id": "alphabot-202640-xlk", "status": "new"
    }])
    monkeypatch.setattr(auto_paper, "build_plan", lambda: pytest.fail("Plan built while order pending"))
    assert auto_paper.run_automatic_paper()["status"] == "waiting"


def test_full_order_history_stops_before_planning(monkeypatch):
    setup_run(monkeypatch, [], prior=[{"symbol": "SPY", "status": "filled"}] * 500)
    monkeypatch.setattr(auto_paper, "build_plan", lambda: pytest.fail("Unverified order history"))
    with pytest.raises(RuntimeError, match="history is full"):
        auto_paper.run_automatic_paper()
