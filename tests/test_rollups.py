"""MOD-08 / MOD-09: progress and estimate rollups work over leaves and terminal states."""
import pytest
from fastapi.testclient import TestClient

from reqtool.api import create_app
from tests.conftest import make_req


@pytest.fixture
def c(repo_root):
    return TestClient(create_app(repo_root))


def _set_status(c, uid, status):
    c.app.state.store.requirements[uid]["status"] = status


def _story(c, parent, est=None, status=None, **kw):
    body = {"title": "s", "req_type": "story", "parentId": parent}
    if est is not None:
        body["estimate"] = est
    r = make_req(c, **body, **kw)
    if status:
        _set_status(c, r["uid"], status)
    return r["uid"]


def _progress(c, uid):
    r = c.get(f"/requirements/{uid}/progress")
    assert r.status_code == 200, r.text
    return r.json()


def test_progress_excludes_root_and_cancelled(c):
    epic = make_req(c, title="e", req_type="epic")["uid"]
    _story(c, epic, status="done")
    _story(c, epic, status="cancelled")
    _story(c, epic)
    p = _progress(c, epic)
    assert (p["total_items"], p["done_items"], p["progress_pct"]) == (2, 1, 50.0)


def test_active_is_not_done(c):
    epic = make_req(c, title="e", req_type="epic")["uid"]
    _story(c, epic, status="active")
    p = _progress(c, epic)
    assert p["done_items"] == 0 and p["progress_pct"] == 0.0


def test_progress_weighted_by_leaf_estimate_only(c):
    ini = make_req(c, title="i", req_type="epic", estimate=100)["uid"]  # own estimate ignored
    _story(c, ini, est=3, status="done")
    _story(c, ini, est=1)
    p = _progress(c, ini)
    assert p["total_estimate"] == 4 and p["progress_pct"] == 75.0


def test_nested_parents_are_not_counted_as_items(c):
    top = make_req(c, title="t", req_type="epic")["uid"]
    mid = make_req(c, title="m", req_type="epic", parentId=top)["uid"]
    _story(c, mid, status="done")
    _story(c, mid)
    p = _progress(c, top)
    assert p["total_items"] == 2 and p["done_items"] == 1


def test_leaf_with_no_children_uses_own_state(c):
    leaf = _story(c, None, status="done")
    assert _progress(c, leaf)["progress_pct"] == 100.0


def test_estimate_rollup_is_recursive_over_leaves(c):
    top = make_req(c, title="t", req_type="epic", estimate=50)["uid"]
    mid = make_req(c, title="m", req_type="epic", parentId=top, estimate=40)["uid"]
    _story(c, mid, est=3)
    _story(c, mid, est=5)
    _story(c, top, est=2)
    _story(c, top, est=9, status="cancelled")
    r = c.get(f"/requirements/{top}/rollup").json()
    assert r["estimate_rollup"] == 10.0


def test_estimate_rollup_none_without_leaf_estimates(c):
    top = make_req(c, title="t", req_type="epic")["uid"]
    _story(c, top)
    assert c.get(f"/requirements/{top}/rollup").json()["estimate_rollup"] is None
