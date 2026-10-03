"""SEC-12: the signing key and user store must be private and git-ignored."""
import os
import stat
import sys

import pytest

from reqtool import auth
from reqtool.auth import UserStore, _get_secret_key, ensure_secrets_ignored

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")


@posix_only
def test_secret_key_created_owner_only(tmp_path):
    key = _get_secret_key(tmp_path)
    assert len(key) == 32
    mode = stat.S_IMODE(os.stat(tmp_path / ".reqtool" / ".secret_key").st_mode)
    assert mode == 0o600


@posix_only
def test_existing_loose_key_is_tightened(tmp_path):
    p = tmp_path / ".reqtool" / ".secret_key"
    p.parent.mkdir()
    p.write_bytes(b"k" * 32)
    os.chmod(p, 0o644)
    assert _get_secret_key(tmp_path) == b"k" * 32
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_key_is_stable_across_calls(tmp_path):
    assert _get_secret_key(tmp_path) == _get_secret_key(tmp_path)


def test_gitignore_gets_secret_entries(tmp_path):
    (tmp_path / ".gitignore").write_text("exports/")  # no trailing newline
    ensure_secrets_ignored(tmp_path)
    ensure_secrets_ignored(tmp_path)  # idempotent
    lines = (tmp_path / ".gitignore").read_text().splitlines()
    assert lines[0] == "exports/"
    assert lines.count(".reqtool/.secret_key") == 1
    assert lines.count(".reqtool/users.yaml") == 1


def test_creating_key_and_users_updates_gitignore(tmp_path):
    _get_secret_key(tmp_path)
    UserStore(tmp_path).create_user("u", "longenough1", role="admin")
    text = (tmp_path / ".gitignore").read_text()
    assert ".reqtool/.secret_key" in text and ".reqtool/users.yaml" in text


@posix_only
def test_users_file_owner_only(tmp_path):
    UserStore(tmp_path).create_user("u", "longenough1", role="admin")
    assert stat.S_IMODE(os.stat(tmp_path / ".reqtool" / "users.yaml").st_mode) == 0o600


def test_req_init_ignores_secrets(tmp_path):
    import subprocess
    from click.testing import CliRunner
    from reqtool.cli import cli
    root = tmp_path / "r"
    root.mkdir()
    res = CliRunner().invoke(cli, ["init", "demo", "--repo", str(root)])
    assert res.exit_code == 0, res.output
    assert ".reqtool/.secret_key" in (root / ".gitignore").read_text()
    _get_secret_key(root)
    out = subprocess.run(["git", "status", "--porcelain", "--ignored"], cwd=root, capture_output=True, text=True).stdout
    assert "!! .reqtool/.secret_key" in out
