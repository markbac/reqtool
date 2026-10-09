"""DAT-14: invalid config writes must be rejected and must not corrupt the repo."""
from reqtool.store import Store


def _snapshot(root):
    return {p.name: p.read_bytes() for p in (root / ".reqtool").glob("*.yaml")}


def test_bad_config_is_422_and_file_unchanged(client, repo_root):
    before = _snapshot(repo_root)
    r = client.put("/config", json={"git": "not-an-object"})
    assert r.status_code == 422, r.text
    assert _snapshot(repo_root) == before


def test_bad_workflow_is_422_and_file_unchanged(client, repo_root):
    before = _snapshot(repo_root)
    r = client.put("/workflow", json={"states": "oops", "transitions": 5})
    assert r.status_code == 422, r.text
    assert _snapshot(repo_root) == before


def test_bad_enums_is_422_and_file_unchanged(client, repo_root):
    before = _snapshot(repo_root)
    r = client.put("/enums/repo", json={"domain": {"not": "a list"}})
    assert r.status_code == 422, r.text
    assert _snapshot(repo_root) == before


def test_repo_still_loads_after_rejected_writes(client, repo_root):
    client.put("/config", json={"git": "x"})
    client.put("/workflow", json={"states": 1})
    client.put("/enums/repo", json={"domain": 1})
    Store(repo_root).load()  # would raise before the fix if anything was persisted


def test_valid_writes_still_work(client):
    wf = client.get("/workflow").json()
    assert client.put("/workflow", json=wf).status_code == 200
    en = client.get("/enums/repo").json()
    assert client.put("/enums/repo", json=en).status_code == 200
    assert client.put("/config", json={"repo_title": "New title"}).json()["repo_title"] == "New title"
