"""SEC-14: only local callers may pick server filesystem paths."""
import pytest
from fastapi.testclient import TestClient

from reqtool.api import create_app


def _remote(repo_root):
    return TestClient(create_app(repo_root), client=("203.0.113.9", 4444))


def test_remote_cannot_init_or_switch(repo_root, tmp_path):
    c = _remote(repo_root)
    target = tmp_path / "evil"
    assert c.post("/repo/init", json={"path": str(target)}).status_code == 403
    assert not target.exists()
    assert c.post("/repo/switch", json={"path": str(repo_root)}).status_code == 403


def test_local_can_init_and_switch(client, tmp_path):
    target = tmp_path / "newrepo"
    r = client.post("/repo/init", json={"path": str(target), "mode": "bare"})
    assert r.status_code == 201, r.text
    assert (target / ".reqtool" / "config.yaml").exists()
    assert client.post("/repo/switch", json={"path": str(target)}).status_code == 200


def test_disable_flag(client, tmp_path, monkeypatch):
    monkeypatch.setenv("REQTOOL_DISABLE_REPO_SWITCH", "1")
    assert client.post("/repo/init", json={"path": str(tmp_path / "x")}).status_code == 403
    assert not (tmp_path / "x").exists()


def test_roots_allowlist(client, tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("REQTOOL_REPO_ROOTS", str(allowed))
    assert client.post("/repo/init", json={"path": str(tmp_path / "outside")}).status_code == 403
    assert not (tmp_path / "outside").exists()
    assert client.post("/repo/init", json={"path": str(allowed / ".." / "outside2")}).status_code == 403
    assert client.post("/repo/init", json={"path": str(allowed / "ok"), "mode": "bare"}).status_code == 201
