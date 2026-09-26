from fastapi.testclient import TestClient
from src.main import app
import base64

def test_health():
    r=TestClient(app).get("/health")
    assert r.status_code==200
    assert r.json()["ok"] is True


def test_dashboard_fails_closed_without_login_configuration(monkeypatch):
    monkeypatch.delenv("ALPHABOT_DASHBOARD_USER", raising=False)
    monkeypatch.delenv("ALPHABOT_DASHBOARD_PASSWORD", raising=False)
    client = TestClient(app)
    assert client.get("/").status_code == 503
    assert client.post("/api/paper/execute", json={"plan_id": "test", "confirm_paper": True}).status_code == 503


def test_paper_endpoints_require_login_before_execution(monkeypatch):
    monkeypatch.setenv("ALPHABOT_DASHBOARD_USER", "operator")
    monkeypatch.setenv("ALPHABOT_DASHBOARD_PASSWORD", "test-password")
    client = TestClient(app)
    response = client.post("/api/paper/execute", json={"plan_id": "test", "confirm_paper": True})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Basic realm="ALPHABOT"'
    assert client.get("/api/paper/account").status_code == 401
    assert client.get("/docs").status_code == 401
    token = base64.b64encode(b"operator:test-password").decode()
    assert client.get("/", headers={"Authorization": f"Basic {token}"}).status_code == 200
