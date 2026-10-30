"""#346: the operating mode comes from config, can be overridden per machine, and sets the default auth."""
import subprocess

import pytest
import yaml
from click.testing import CliRunner
from fastapi.testclient import TestClient

from reqtool.api import create_app
from reqtool.cli import cli
from reqtool.features.doctor import run_doctor
from reqtool.modes import default_auth, resolve_mode
from reqtool.store import Store


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv("REQTOOL_MODE", raising=False)
    monkeypatch.delenv("REQTOOL_AUTH", raising=False)


def _set_mode(root, mode):
    (root / ".reqtool" / "config.yaml").write_text(yaml.safe_dump({"mode": mode}))


def test_resolve_order_explicit_env_config_default(monkeypatch):
    assert resolve_mode() == "local"
    assert resolve_mode("shared-repo") == "shared-repo"
    monkeypatch.setenv("REQTOOL_MODE", "server")
    assert resolve_mode("shared-repo") == "server"
    assert resolve_mode("shared-repo", "local") == "local"
    monkeypatch.delenv("REQTOOL_MODE")
    with pytest.raises(ValueError):
        resolve_mode("cluster")


def test_default_auth_follows_mode():
    assert default_auth("server") == "required"
    assert default_auth("local") == default_auth("shared-repo") == "local"


def test_existing_repository_without_mode_is_local(repo_root):
    c = TestClient(create_app(repo_root))
    assert c.get("/health").json()["operating_mode"] == "local"
    body = c.get("/permissions").json()
    assert body["mode"] == "local" and body["operating_mode"] == "local"


def test_shared_repo_mode_is_reported_and_stays_local_auth(repo_root):
    _set_mode(repo_root, "shared-repo")
    c = TestClient(create_app(repo_root))
    body = c.get("/permissions").json()
    assert body["operating_mode"] == "shared-repo" and body["mode"] == "local"


def test_server_mode_requires_login_by_default(repo_root):
    _set_mode(repo_root, "server")
    c = TestClient(create_app(repo_root))
    assert c.get("/health").json()["operating_mode"] == "server"
    assert c.get("/requirements").status_code == 401


def test_env_override_wins_over_config(repo_root, monkeypatch):
    _set_mode(repo_root, "shared-repo")
    monkeypatch.setenv("REQTOOL_MODE", "local")
    assert TestClient(create_app(repo_root)).get("/health").json()["operating_mode"] == "local"


def test_req_mode_sets_and_shows(repo_root):
    runner = CliRunner()
    r = runner.invoke(cli, ["mode", "shared-repo", "--repo", str(repo_root)])
    assert r.exit_code == 0, r.output
    assert yaml.safe_load((repo_root / ".reqtool" / "config.yaml").read_text())["mode"] == "shared-repo"
    r = runner.invoke(cli, ["mode", "--repo", str(repo_root)])
    assert "Operating mode: shared-repo" in r.output


def test_doctor_flags_shared_repo_without_remote(repo_root):
    _set_mode(repo_root, "shared-repo")
    s = Store(repo_root)
    s.load()
    assert "not_git_repo" in {c["code"] for c in run_doctor(s)["checks"]}
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    assert "no_remote" in {c["code"] for c in run_doctor(s)["checks"]}
    subprocess.run(["git", "remote", "add", "origin", "https://example.com/r.git"], cwd=repo_root, check=True)
    codes = {c["code"] for c in run_doctor(s)["checks"]}
    assert not codes & {"not_git_repo", "no_remote"}
