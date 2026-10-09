"""SEC-07: fetch_remote_module must not allow git option or transport injection."""
import subprocess

import pytest

from reqtool.fileio import save_yaml
from reqtool.store import _validate_remote_ref, _validate_remote_url


@pytest.mark.parametrize("url", [
    "https://github.com/org/repo.git", "http://host/repo", "ssh://git@host/org/repo.git",
    "git://host/repo.git", "git@github.com:org/repo.git",
])
def test_valid_urls(url):
    _validate_remote_url(url)


@pytest.mark.parametrize("url", [
    "", "--upload-pack=touch /tmp/pwn", "-oProxyCommand=x", "ext::sh -c 'touch /tmp/pwn'",
    "file:///etc", "/etc/passwd", "../relative", "C:\\repo", "https://host/a b", "https://", "ftp://h/r",
    "https://host/repo\n--upload-pack=x",
])
def test_invalid_urls(url):
    with pytest.raises(ValueError):
        _validate_remote_url(url)


@pytest.mark.parametrize("ref", ["main", "v1.2.3", "release/1.0", "a1b2c3"])
def test_valid_refs(ref):
    _validate_remote_ref(ref)


@pytest.mark.parametrize("ref", ["--upload-pack=x", "-b", "", "a..b", "a b", "a;b", "x" * 201])
def test_invalid_refs(ref):
    with pytest.raises(ValueError):
        _validate_remote_ref(ref)


def _manifest(store, **fields):
    d = store.root / "modules" / "m1"
    d.mkdir(parents=True, exist_ok=True)
    save_yaml(d / "_module.yaml", {"id": "m1", **fields})


def test_fetch_rejects_option_remote_and_executes_nothing(store, tmp_path):
    marker = tmp_path / "pwned"
    _manifest(store, git_remote=f"--upload-pack=touch {marker}", git_ref="main")
    with pytest.raises(ValueError):
        store.fetch_remote_module("m1")
    assert not marker.exists()


def test_fetch_rejects_option_ref(store, tmp_path):
    _manifest(store, git_remote="https://example.invalid/r.git", git_ref="--upload-pack=x")
    with pytest.raises(ValueError):
        store.fetch_remote_module("m1")


def test_fetch_rejects_local_path_and_file_scheme(store, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=src, check=True)
    for remote in (str(src), f"file://{src}"):
        _manifest(store, git_remote=remote, git_ref="main")
        with pytest.raises(ValueError):
            store.fetch_remote_module("m1")


def test_clone_failure_is_reported_not_swallowed(store):
    _manifest(store, git_remote="https://127.0.0.1:1/none.git", git_ref="main")
    with pytest.raises(ValueError, match="git clone failed"):
        store.fetch_remote_module("m1")
