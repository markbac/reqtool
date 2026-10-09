"""SEC-03: CORS is limited to local origins plus an explicit allowlist."""
from fastapi.testclient import TestClient

from reqtool.api import create_app


def _preflight(c, origin):
    return c.options("/health", headers={
        "Origin": origin, "Access-Control-Request-Method": "GET",
    })


def test_foreign_origin_not_allowed(client):
    for origin in ("https://evil.example", "http://localhost.evil.example", "http://127.0.0.1.evil.example", "null"):
        r = client.get("/health", headers={"Origin": origin})
        assert "access-control-allow-origin" not in r.headers, origin
        assert "access-control-allow-origin" not in _preflight(client, origin).headers, origin


def test_local_origins_allowed(client):
    for origin in ("http://localhost:5173", "http://127.0.0.1:8765", "http://localhost", "http://[::1]:3000"):
        r = client.get("/health", headers={"Origin": origin})
        assert r.headers.get("access-control-allow-origin") == origin, origin


def test_never_wildcard_and_no_credentials(client):
    r = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") != "*"
    assert "access-control-allow-credentials" not in r.headers


def test_env_allowlist(repo_root, monkeypatch):
    monkeypatch.setenv("REQTOOL_CORS_ORIGINS", "https://reqs.corp.example, https://other.example")
    c = TestClient(create_app(repo_root))
    assert c.get("/health", headers={"Origin": "https://reqs.corp.example"}).headers["access-control-allow-origin"] == "https://reqs.corp.example"
    assert "access-control-allow-origin" not in c.get("/health", headers={"Origin": "https://evil.example"}).headers
