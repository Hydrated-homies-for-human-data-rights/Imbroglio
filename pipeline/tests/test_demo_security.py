"""Demo console security: password gate, input validation, concurrency cap."""

import base64
import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))

PASSWORD = "correct-horse-battery"


def _basic(user, pw):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


@pytest.fixture
def app_module(monkeypatch):
    monkeypatch.setenv("IMBROGLIO_PASSWORD", PASSWORD)
    monkeypatch.setenv("IMBROGLIO_USER", "team")
    import app as demo_app
    demo_app = importlib.reload(demo_app)
    monkeypatch.setattr(demo_app, "db_reachable", lambda: False)  # no DB needed
    return demo_app


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)


AUTH = _basic("team", PASSWORD)


def test_everything_requires_password(client):
    for path in ("/", "/api/health", "/api/services", "/api/service/notion.so"):
        r = client.get(path)
        assert r.status_code == 401, path
        assert "Basic" in r.headers["www-authenticate"]
    assert client.post("/api/analyze", json={"domain": "notion.so"}).status_code == 401


def test_wrong_credentials_rejected(client):
    assert client.get("/api/health", headers=_basic("team", "wrong")).status_code == 401
    assert client.get("/api/health", headers=_basic("admin", PASSWORD)).status_code == 401
    assert client.get("/api/health", headers={"Authorization": "Basic !!!notbase64"}).status_code == 401


def test_correct_credentials_accepted(client):
    r = client.get("/api/health", headers=AUTH)
    assert r.status_code == 200
    assert r.headers["x-frame-options"] == "DENY"


def test_healthz_open_and_reveals_nothing(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_api_docs_disabled(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path, headers=AUTH).status_code == 404


@pytest.mark.parametrize("domain", ["169.254.169.254", "127.0.0.1", "localhost",
                                    "not a domain", "x" * 300])
def test_analyze_rejects_non_domains(client, domain):
    r = client.post("/api/analyze", json={"domain": domain}, headers=AUTH)
    assert r.status_code in (400, 422)


def test_concurrency_cap(client, app_module):
    for _ in range(app_module.MAX_CONCURRENT):
        assert app_module._slots.acquire(blocking=False)
    try:
        r = client.post("/api/analyze", json={"domain": "notion.so"}, headers=AUTH)
        assert r.status_code == 429
    finally:
        for _ in range(app_module.MAX_CONCURRENT):
            app_module._slots.release()


def test_slot_released_after_run(client, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "analyze", lambda *a, **k: [])
    for _ in range(app_module.MAX_CONCURRENT + 2):  # more runs than slots
        r = client.post("/api/analyze", json={"domain": "notion.so"}, headers=AUTH)
        assert r.status_code == 200
        assert '"type": "result"' in r.text
