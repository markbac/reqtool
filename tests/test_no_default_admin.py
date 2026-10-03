"""SEC-04: no well-known default administrator account."""
from click.testing import CliRunner

from reqtool.auth import UserStore, hash_password
from reqtool.cli import cli
from reqtool.fileio import save_yaml


def test_no_users_file_or_account_is_created_implicitly(repo_root, client):
    assert UserStore(repo_root).load_users() == {}
    assert not (repo_root / ".reqtool" / "users.yaml").exists()
    r = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 401
    assert not (repo_root / ".reqtool" / "users.yaml").exists()  # login must not seed either


def test_legacy_default_account_is_refused_and_detected(repo_root, client):
    h, salt = hash_password("admin123")
    save_yaml(repo_root / ".reqtool" / "users.yaml", {"users": {"admin": {
        "username": "admin", "role": "admin", "password_hash": h, "salt": salt}}})
    us = UserStore(repo_root)
    assert us.has_default_credentials() is True
    assert us.authenticate("admin", "admin123") is None
    assert client.post("/auth/login", json={"username": "admin", "password": "admin123"}).status_code == 401


def test_changed_admin_password_is_not_flagged(repo_root):
    us = UserStore(repo_root)
    us.create_user("admin", "a-strong-passphrase", role="admin")
    assert us.has_default_credentials() is False
    assert us.authenticate("admin", "a-strong-passphrase") is not None


def test_cli_creates_first_admin_and_resets_password(repo_root):
    r = CliRunner()
    out = r.invoke(cli, ["user", "add", "alice", "--role", "admin", "--password", "longenough1", "--repo", str(repo_root)])
    assert out.exit_code == 0, out.output
    assert UserStore(repo_root).authenticate("alice", "longenough1")["role"] == "admin"
    out = r.invoke(cli, ["user", "passwd", "alice", "--password", "another-pass-2", "--repo", str(repo_root)])
    assert out.exit_code == 0, out.output
    assert UserStore(repo_root).authenticate("alice", "another-pass-2") is not None
    assert UserStore(repo_root).authenticate("alice", "longenough1") is None


def test_cli_rejects_short_password_and_unknown_user(repo_root):
    r = CliRunner()
    assert r.invoke(cli, ["user", "add", "bob", "--password", "short", "--repo", str(repo_root)]).exit_code != 0
    assert r.invoke(cli, ["user", "passwd", "ghost", "--password", "longenough1", "--repo", str(repo_root)]).exit_code != 0
