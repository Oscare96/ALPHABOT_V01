import os
from typing import Optional
import httpx

PAPER_BASE_URL = "https://paper-api.alpaca.markets"
_session_credentials: dict[str, str] = {}


def configure(key_id: str, secret_key: str) -> None:
    _session_credentials["key_id"] = key_id.strip()
    _session_credentials["secret_key"] = secret_key.strip()


def clear_runtime_credentials() -> None:
    _session_credentials.clear()


def _credentials() -> tuple[Optional[str], Optional[str], str]:
    key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or _session_credentials.get("key_id")
    secret = os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY") or _session_credentials.get("secret_key")
    source = "environment" if (os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")) else ("runtime" if key else "none")
    return key, secret, source


def configured() -> dict:
    key, secret, source = _credentials()
    return {"configured": bool(key and secret), "source": source, "paper_only": True}


def _headers() -> dict[str, str]:
    key, secret, _ = _credentials()
    if not key or not secret:
        raise RuntimeError("Alpaca paper credentials are not configured")
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}


def _request(method: str, path: str, **kwargs):
    with httpx.Client(timeout=20.0) as client:
        r = client.request(method, f"{PAPER_BASE_URL}{path}", headers=_headers(), **kwargs)
        r.raise_for_status()
        if r.status_code == 204 or not r.content:
            return {}
        return r.json()


def account() -> dict:
    return _request("GET", "/v2/account")


def positions() -> list[dict]:
    return _request("GET", "/v2/positions")


def orders(status: str = "all", limit: int = 100) -> list[dict]:
    return _request("GET", "/v2/orders", params={"status": status, "limit": limit, "direction": "desc"})


def clock() -> dict:
    return _request("GET", "/v2/clock")


def submit_market_order(symbol: str, notional: float, side: str, client_order_id: str) -> dict:
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    if notional <= 0:
        raise ValueError("notional must be positive")
    payload = {
        "symbol": symbol,
        "notional": f"{notional:.2f}",
        "side": side,
        "type": "market",
        "time_in_force": "day",
        "client_order_id": client_order_id,
    }
    return _request("POST", "/v2/orders", json=payload)


def close_position(symbol: str) -> dict:
    return _request("DELETE", f"/v2/positions/{symbol}")
