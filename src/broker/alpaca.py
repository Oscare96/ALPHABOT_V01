import os
from typing import Optional
import httpx

PAPER_BASE_URL = "https://paper-api.alpaca.markets"
_session_credentials: dict[str, str] = {}


def configure(key_id: str, secret_key: str) -> None:
    # Runtime-only fallback for the dashboard connection box. Railway env vars
    # remain the recommended persistent storage because runtime memory is lost
    # on redeploy/restart.
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


def account() -> dict:
    with httpx.Client(timeout=15.0) as client:
        r = client.get(f"{PAPER_BASE_URL}/v2/account", headers=_headers())
        r.raise_for_status()
        return r.json()


def positions() -> list[dict]:
    with httpx.Client(timeout=15.0) as client:
        r = client.get(f"{PAPER_BASE_URL}/v2/positions", headers=_headers())
        r.raise_for_status()
        return r.json()


def orders(status: str = "all", limit: int = 100) -> list[dict]:
    with httpx.Client(timeout=15.0) as client:
        r = client.get(f"{PAPER_BASE_URL}/v2/orders", headers=_headers(), params={"status": status, "limit": limit, "direction": "desc"})
        r.raise_for_status()
        return r.json()
