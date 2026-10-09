"""SEC-13: user-supplied refs must not be able to inject git options."""
import subprocess

import pytest
from fastapi.testclient import TestClient

from reqtool.api import create_app
from reqtool.git_ops import InvalidRef, validate_ref


@pytest.mark.parametrize("ref", ["HEAD", "HEAD~1", "HEAD^", "main", "v1.2.3", "baseline/b1", "a1b2c3d", "feature/x-y"])
def test_valid_refs(ref):
    assert validate_ref(ref) == ref


@pytest.mark.parametrize("ref", [
    "--output=/tmp/pwn", "-x", "", " HEAD", "a b", "a..b", "a\nb", "x" * 300, "foo.lock", "--help",
])
def test_invalid_refs(ref):
    with pytest.raises(InvalidRef):
        validate_ref(ref)


def _client(repo_root):
    for a in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
              ["commit", "-q", "--allow-empty", "-m", "a"], ["commit", "-q", "--allow-empty", "-m", "b"]):
        subprocess.run(["git", *a], cwd=repo_root, check=True, capture_output=True)
    return TestClient(create_app(repo_root))


def test_diff_rejects_option_injection_and_writes_nothing(repo_root, tmp_path):
    c = _client(repo_root)
    target = tmp_path / "pwned.txt"
    r = c.get("/diff", params={"since": f"--output={target}"})
    assert r.status_code == 422, r.text
    assert not target.exists()
    r = c.get("/diff", params={"v1": "HEAD", "v2": "--output=" + str(target)})
    assert r.status_code == 422
    assert not target.exists()


def test_diff_still_works(repo_root):
    c = _client(repo_root)
    r = c.get("/diff", params={"since": "HEAD~1"})
    assert r.status_code == 200, r.text
    assert r.json()["ref"] == "HEAD~1"


def test_baseline_name_cannot_be_an_option(repo_root):
    c = _client(repo_root)
    r = c.post("/baselines", json={"name": "ok name"})
    assert r.status_code == 201
    r = c.post("/baselines", json={"name": "x..y"})
    assert r.status_code == 422
