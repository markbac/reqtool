"""DAT-17: GET requests never write files."""
import re
from tests.conftest import make_req


def _snapshot(root):
    return {str(p.relative_to(root)): p.stat().st_mtime_ns for p in root.rglob("*")
            if p.is_file() and ".git" not in p.parts}


def _simple_get_paths(client):
    paths = []
    for path, ops in client.get("/openapi.json").json()["paths"].items():
        if "get" in ops and not re.search(r"\{", path) and path not in ("/ws",):
            paths.append(path)
    return sorted(paths)


def test_fresh_repo_gets_do_not_touch_the_tree(client):
    root = client.app.state.store.root
    before = _snapshot(root)
    paths = _simple_get_paths(client)
    assert "/iterations" in paths and "/automation/rules" in paths
    for path in paths:
        client.get(path)  # status does not matter, only that nothing is written
    assert _snapshot(root) == before


def test_defaults_are_still_served_and_first_save_persists(client):
    root = client.app.state.store.root
    its = client.get("/iterations").json()
    assert len(its) >= 3 and not (root / ".reqtool" / "iterations.yaml").exists()
    rules = client.get("/automation/rules").json()
    assert len(rules) >= 2 and not (root / ".reqtool" / "automation_rules.yaml").exists()
    assert client.put("/automation/rules", json=rules).status_code == 200
    assert (root / ".reqtool" / "automation_rules.yaml").exists()


def test_gets_after_content_exists_are_also_readonly(client):
    for i in range(3):
        make_req(client, title=f"R{i}")
    root = client.app.state.store.root
    before = _snapshot(root)
    for path in _simple_get_paths(client):
        client.get(path)
    assert _snapshot(root) == before


def test_example_rules_do_not_run_until_saved(client):
    client.get("/automation/rules")  # shows the examples
    r = make_req(client, title="S", req_type="safety")
    assert "ASIL-D" not in client.get(f"/requirements/{r['uid']}").json().get("tags", [])
