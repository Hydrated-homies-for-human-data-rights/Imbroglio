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
    monkeypatch.setenv("EMBEDDED_WORKER", "0")
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
    assert client.post("/api/requests", json={"domain": "notion.so"}).status_code == 401
    assert client.get("/api/requests/1").status_code == 401


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


def test_api_docs_behind_password(client):
    for path in ("/docs", "/redoc", "/openapi.json"):  # old default paths stay off
        assert client.get(path, headers=AUTH).status_code == 404
    assert client.get("/v1/docs").status_code == 401
    assert client.get("/v1/openapi.json").status_code == 401
    spec = client.get("/v1/openapi.json", headers=AUTH).json()
    assert "/v1/sites/{domain}" in spec["paths"]


@pytest.mark.parametrize("domain", ["169.254.169.254", "127.0.0.1", "localhost",
                                    "not a domain", "x" * 300])
def test_request_rejects_non_domains(client, domain):
    r = client.post("/api/requests", json={"domain": domain}, headers=AUTH)
    assert r.status_code in (400, 422)


def test_request_needs_database(client):
    r = client.post("/api/requests", json={"domain": "notion.so"}, headers=AUTH)
    assert r.status_code == 503  # fixture stubs the DB as unreachable


def test_audit_routes_require_password(client):
    for path in ("/audit", "/api/audit/next", "/api/audit/summary"):
        assert client.get(path).status_code == 401, path
    assert client.post("/api/audit", json={"attempt_id": 1, "verdict": "correct"}).status_code == 401


def test_audit_rejects_bad_input(client):
    r = client.post("/api/audit", json={"attempt_id": 1, "verdict": "DROP TABLE"}, headers=AUTH)
    assert r.status_code == 422
    r = client.post("/api/audit", json={"attempt_id": 1, "verdict": "missed",
                                        "correct_url": "javascript:alert(1)"}, headers=AUTH)
    assert r.status_code == 400


def test_audit_metrics_math(app_module):
    # 80 found, 20 missed. Reviewed found: 9 correct, 1 wrong -> precision 0.9.
    # Reviewed missed: 1 had a policy, 3 had none -> 25% of misses are real misses.
    # TP ~ 80 * 0.9 = 72, FN ~ 20 * 0.25 = 5 -> recall 72 / 77.
    m = app_module.audit_metrics({
        "totals": {"found": 80, "missed": 20},
        "verdicts": {"found:correct": 9, "found:wrong": 1, "missed:missed": 1, "missed:none": 3},
    })
    assert m["precision"] == 0.9
    assert m["missed_with_policy_rate"] == 0.25
    assert abs(m["recall_estimate"] - 72 / 77) < 1e-9
    assert m["reviewed"] == {"found": 10, "missed": 4}


def test_audit_metrics_empty(app_module):
    m = app_module.audit_metrics({"totals": {}, "verdicts": {}})
    assert m["precision"] is None and m["recall_estimate"] is None
