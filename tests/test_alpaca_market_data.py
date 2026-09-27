import httpx
import pytest

from src.data import alpaca_market_data


def test_alpaca_paginates_and_keeps_exchange_dates(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "paper-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "paper-secret")
    real_client = httpx.Client
    requests = []

    def respond(request):
        requests.append(request)
        symbol = "SPY" if len(requests) == 1 else "XLK"
        body = {"bars": {symbol: [{"t": "2024-01-03T05:00:00Z", "o": 99,
                                  "h": 101, "l": 98, "c": 100, "v": 1234}]},
                "next_page_token": "second" if len(requests) == 1 else None}
        return httpx.Response(200, json=body)

    monkeypatch.setattr(alpaca_market_data.httpx, "Client",
                        lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw))
    result = alpaca_market_data.download_alpaca_market_data(
        start="2024-01-01", end="2024-02-01", symbols=["SPY", "XLK"])
    assert len(requests) == 2
    assert requests[0].url.params["feed"] == "iex"
    assert requests[0].url.params["adjustment"] == "all"
    assert requests[1].url.params["page_token"] == "second"
    assert requests[0].headers["APCA-API-KEY-ID"] == "paper-key"
    assert result["XLK"].index[0].date().isoformat() == "2024-01-03"
    assert result["SPY"]["close"].iloc[0] == 100


def test_alpaca_requires_credentials(monkeypatch):
    for name in ("ALPACA_API_KEY", "APCA_API_KEY_ID", "ALPACA_SECRET_KEY", "APCA_API_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="not configured"):
        alpaca_market_data.download_alpaca_market_data(symbols=["SPY"])
