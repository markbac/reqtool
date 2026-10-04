"""ENH-01..07 and FEAT-01..12: traceability views, readiness gate, quality rules, query language,
JUnit ingestion, doctor, trend, reviews, notifications, change sets, snapshot and module management."""
import io
import subprocess
import zipfile

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from reqtool.api import create_app
from tests.conftest import make_req


def git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def seed(root):
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed", "--allow-empty")


@pytest.fixture
def c(repo_root):
    return TestClient(create_app(repo_root))


def rel(target, kind="satisfies"):
    return {"type": kind, "target": {"uid": target}}


# --- ENH-01 / ENH-02 / ENH-03 / ENH-06 ---------------------------------------------

def test_trace_lists_upstream_downstream_and_gaps(c):
    top = make_req(c, title="Top level requirement")
    low = make_req(c, title="Lower level requirement", relationships=[rel(top["uid"])])
    t = c.get(f"/requirements/{top['uid']}/trace").json()
    assert [d["uid"] for d in t["downstream"]] == [low["uid"]]
    assert "no_downstream" not in t["gaps"] and "no_upstream" in t["gaps"]
    lo = c.get(f"/requirements/{low['id']}/trace").json()  # human id accepted
    assert [u["uid"] for u in lo["upstream"]] == [top["uid"]]
    assert "not_verified" in lo["gaps"]
    assert c.get("/requirements/nope/trace").status_code == 404


def test_lifecycle_reports_stage_and_blockers(c):
    r = make_req(c, title="Lifecycle item")
    lc = c.get(f"/requirements/{r['uid']}/lifecycle").json()
    assert lc["stage"] == "draft" and lc["stages"][-1] == "baselined"
    assert any(b["code"] == "trace_gap" for b in lc["blockers"])


def test_overview_counts_and_percentages(c):
    a = make_req(c, title="First requirement")
    make_req(c, title="Second requirement", relationships=[rel(a["uid"])])
    c.put(f"/requirements/{a['uid']}", json={"verification": {"status": "passed"}})
    o = c.get("/overview").json()
    assert o["counts"]["requirements"] == 2
    assert o["percentages"]["verified"] == 50.0 and o["percentages"]["traced"] == 50.0
    assert c.get("/overview?product=missing").status_code == 404


def test_roadmap_nests_strategic_items_with_progress(c):
    theme = make_req(c, title="Theme one", req_type="theme")
    ini = make_req(c, title="Initiative one", req_type="initiative", parentId=theme["uid"])
    epic = make_req(c, title="Epic one", req_type="epic", parentId=ini["uid"])
    make_req(c, title="Story one", req_type="story", parentId=epic["uid"])
    road = c.get("/roadmap").json()
    assert [n["uid"] for n in road] == [theme["uid"]]
    assert road[0]["children"][0]["children"][0]["uid"] == epic["uid"]
    assert road[0]["children_count"] == 1 and road[0]["progress_pct"] == 0.0


# --- FEAT-03 ------------------------------------------------------------------------

def test_impact_preview_names_items_that_would_become_suspect(c):
    top = make_req(c, title="Upstream requirement")
    low = make_req(c, title="Downstream requirement", relationships=[rel(top["uid"])])
    p = c.post(f"/requirements/{top['uid']}/impact-preview", json={"title": "Changed title"}).json()
    assert p["content_changed"] and [s["uid"] for s in p["would_become_suspect"]] == [low["uid"]]
    same = c.post(f"/requirements/{top['uid']}/impact-preview", json={"title": top["title"]}).json()
    assert not same["content_changed"] and same["would_become_suspect"] == []
    # previewing changes nothing
    assert c.get(f"/requirements/{top['uid']}").json()["title"] == top["title"]


# --- FEAT-01 ------------------------------------------------------------------------

def test_gate_flags_unverified_safety_and_suspect_links(c, repo_root):
    top = make_req(c, title="Upstream requirement")
    make_req(c, title="Safety related item", safety_related=True, status="approved", relationships=[rel(top["uid"])])
    g = c.get("/gate").json()
    assert not g["ready"]
    codes = {f["code"] for f in g["findings"]}
    assert "unverified_safety" in codes
    c.put(f"/requirements/{top['uid']}", json={"title": "Upstream moved"})
    assert "suspect_link" in {f["code"] for f in c.get("/gate").json()["findings"]}


def test_gate_is_ready_for_an_empty_repository(c):
    assert c.get("/gate").json() == {"ready": True, "count": 0, "findings": []}


def test_gate_flags_dirty_baselines(c, repo_root):
    make_req(c, title="Committed item")
    seed(repo_root)
    assert c.get("/gate").json()["ready"]
    make_req(c, title="Uncommitted item")
    assert "dirty_baseline" in {f["code"] for f in c.get("/gate").json()["findings"]}


def test_gate_cli_exit_codes(repo_root):
    from reqtool.cli import cli
    c = TestClient(create_app(repo_root))
    assert CliRunner().invoke(cli, ["gate", "--repo", str(repo_root)]).exit_code == 0
    make_req(c, title="Safety related item", safety_related=True)
    res = CliRunner().invoke(cli, ["gate", "--repo", str(repo_root)])
    assert res.exit_code == 1 and "unverified_safety" in res.output


# --- FEAT-06 ------------------------------------------------------------------------

def test_quality_rules_have_stable_codes(c):
    f = c.post("/quality/check", json={"title": "x", "description": "The system should be fast and easy etc"}).json()["findings"]
    assert {x["code"] for x in f} == {"Q001", "Q002", "Q003", "Q004", "Q006"}
    good = c.post("/quality/check", json={
        "title": "Brake response", "description": "When the pedal is pressed the system shall brake within 200 ms",
        "acceptance_criteria": 1}).json()["findings"]
    assert good == []
    assert any(x["code"] == "Q005" for x in c.post("/quality/check", json={
        "title": "Two things", "description": "The system shall start in 5 s and shall stop", "acceptance_criteria": 1}).json()["findings"])


def test_quality_for_a_stored_requirement(c):
    r = make_req(c, title="Stored requirement")
    assert c.get(f"/requirements/{r['uid']}/quality").status_code == 200


# --- FEAT-09 ------------------------------------------------------------------------

def test_query_language(c):
    a = make_req(c, title="Brake pedal travel", status="approved", tags=["legacy"])
    make_req(c, title="Steering wheel", status="draft")
    q = lambda s: {r["uid"] for r in c.get("/query", params={"q": s}).json()["results"]}
    assert q("status:approved") == {a["uid"]}
    assert q("brake") == {a["uid"]}
    assert q('"brake pedal" no:verification status:approved') == {a["uid"]}
    assert a["uid"] not in q("-tag:legacy")
    assert q("has:verification") == set()
    assert c.get("/query", params={"q": "status:"}).status_code == 422
    assert c.get("/query", params={"q": '"unclosed'}).status_code == 422


# --- FEAT-05 ------------------------------------------------------------------------

JUNIT = """<?xml version="1.0"?><testsuite>
<testcase classname="tests.brake" name="test_{a}_stops_in_time"/>
<testcase classname="tests.brake" name="test_{b}_alarm"><failure message="boom">trace</failure></testcase>
<testcase classname="tests.misc" name="test_unrelated"/></testsuite>"""


def test_junit_ingestion_sets_verification(c):
    a, b = make_req(c, title="Passing one")["id"], make_req(c, title="Failing one")["id"]
    r = c.post("/test-results?run_url=https://ci.example/1", content=JUNIT.format(a=a, b=b))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tests"] == 3 and body["unmatched_tests"] == ["test_unrelated"]
    assert {u["id"]: u["status"] for u in body["updated"]} == {a: "passed", b: "failed"}
    ver = c.get(f"/requirements/{a}").json()["verification"]
    assert ver["status"] == "passed" and "https://ci.example/1" in ver["note"] and ver["verified_date"]
    again = c.post("/test-results?run_url=https://ci.example/1", content=JUNIT.format(a=a, b=b)).json()
    assert again["updated"] == []  # unchanged results do not add history


def test_junit_rejects_entities_and_bad_xml(c):
    assert c.post("/test-results", content='<!DOCTYPE x [<!ENTITY a "b">]><testsuite/>').status_code == 422
    assert c.post("/test-results", content="not xml").status_code == 422


def test_junit_cli(repo_root, tmp_path):
    from reqtool.cli import cli
    cl = TestClient(create_app(repo_root))
    rid = make_req(cl, title="CLI verified")["id"]
    f = tmp_path / "r.xml"
    f.write_text(JUNIT.format(a=rid, b="NOPE"))
    res = CliRunner().invoke(cli, ["test-results", str(f), "--repo", str(repo_root)])
    assert res.exit_code == 0 and rid in res.output


# --- FEAT-11 ------------------------------------------------------------------------

def test_doctor_flags_unignored_secrets_and_orphans(c, repo_root):
    (repo_root / ".reqtool" / ".secret_key").write_text("x" * 40)
    (repo_root / "requirements" / "stray.yaml").write_text("uid: stray\ntitle: stray\n")
    d = c.get("/doctor").json()
    codes = {x["code"] for x in d["checks"]}
    assert "secret_not_ignored" in codes and not d["ok"]
    (repo_root / ".gitignore").write_text(".reqtool/.secret_key\n")
    assert "secret_not_ignored" not in {x["code"] for x in c.get("/doctor").json()["checks"]}


def test_doctor_finds_parent_problems(c):
    store = c.app.state.store
    r = make_req(c, title="Orphaned child")
    store.requirements[r["uid"]]["parentId"] = "gone"
    assert "missing_parent" in {x["code"] for x in c.get("/doctor").json()["checks"]}


# --- FEAT-12 / ENH-04 ------------------------------------------------------------------

def test_trend_and_field_diff_across_baselines(c, repo_root):
    a = make_req(c, title="Original title")
    seed(repo_root)
    assert c.post("/baselines", json={"name": "v1"}).status_code == 201
    c.app.state.store.update_requirement(a["uid"], {"title": "Edited title", "status": "approved"})
    make_req(c, title="Added later")
    git(repo_root, "add", "-A")
    git(repo_root, "commit", "-q", "-m", "work")
    assert c.post("/baselines", json={"name": "v2"}).status_code == 201
    pts = c.get("/trend").json()["points"]
    assert [p["baseline"] for p in pts] == ["v1", "v2"]
    assert pts[0]["requirements"] == 1 and pts[1]["requirements"] == 2
    assert pts[1]["approved_pct"] == 50.0
    assert pts[1]["churn"] == {"added": 1, "removed": 0, "changed": 1}
    d = c.get("/baselines/field-diff", params={"baseline_a": "v1", "baseline_b": "v2"}).json()
    assert d["summary"] == {"added": 1, "removed": 0, "modified": 1}
    fields = {f["field"]: (f["old"], f["new"]) for f in d["modified"][0]["fields"]}
    assert fields["title"] == ("Original title", "Edited title") and fields["status"] == ("draft", "approved")
    assert c.get("/baselines/field-diff", params={"baseline_a": "nope"}).status_code == 404


# --- ENH-05 ---------------------------------------------------------------------------

def test_duplicate_suggestions_while_authoring(c):
    a = make_req(c, title="Battery charging limit", content={"description": "The charger limits battery charging current"})
    out = c.post("/duplicates/suggest", json={"title": "Limit battery charging", "description": "charging current limit"}).json()
    assert [s["uid"] for s in out["suggestions"]] == [a["uid"]]
    assert c.post("/duplicates/suggest", json={"title": "Wheel alignment tolerance"}).json()["suggestions"] == []
    assert c.post("/duplicates/suggest", json={"title": "Battery charging limit", "exclude_uid": a["uid"]}).json()["suggestions"] == []


# --- ENH-07 ---------------------------------------------------------------------------

def _names(resp):
    assert resp.status_code == 200, resp.text
    return set(zipfile.ZipFile(io.BytesIO(resp.content)).namelist())


def test_audit_package_scope_and_content(c):
    a = make_req(c, title="Selected one")
    make_req(c, title="Left out")
    assert _names(c.get("/export/audit-package")) == {"audit_manifest.json", "cryptographic_signatures.json", "requirements_dump.json"}
    r = c.get("/export/audit-package", params={"scope": "selection", "uids": a["uid"], "include": "requirements,history,traceability,validation,decisions"})
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert set(z.namelist()) == {"audit_manifest.json", "requirements_dump.json", "history.json", "traceability.json",
                                 "validation.json", "decisions.json"}
    import json
    assert [x["uid"] for x in json.loads(z.read("requirements_dump.json"))] == [a["uid"]]
    assert c.get("/export/audit-package", params={"scope": "product", "product": "none"}).status_code == 422
    assert c.get("/export/audit-package", params={"scope": "selection"}).status_code == 422
    assert c.get("/export/audit-package", params={"include": "bogus"}).status_code == 422


# --- FEAT-04 ---------------------------------------------------------------------------

def test_review_requests_are_bound_to_content(c):
    r = make_req(c, title="Reviewed item")
    resp = c.post(f"/requirements/{r['uid']}/review-requests", json={"reviewers": ["alice", "bob"]})
    assert resp.status_code == 201 and len(resp.json()) == 2
    assert [x["status"] for x in c.get("/reviews", params={"reviewer": "alice"}).json()] == ["pending"]
    c.put(f"/requirements/{r['uid']}", json={"title": "Reviewed item changed"})
    assert [x["status"] for x in c.get("/reviews", params={"reviewer": "alice"}).json()] == ["stale"]
    assert c.post(f"/requirements/{r['uid']}/review-requests", json={"reviewers": []}).status_code == 422


def test_approval_bound_to_a_content_hash(c):
    r = make_req(c, title="Approve me")
    c.post(f"/requirements/{r['uid']}/review-requests", json={"reviewers": ["alice"]})
    stale = c.post(f"/requirements/{r['uid']}/approve", json={"approved_by": "alice", "content_hash": "0" * 64})
    assert stale.status_code == 409 and stale.json()["detail"]["error"] == "stale_content"
    current = c.get(f"/requirements/{r['uid']}").json()
    ok = c.post(f"/requirements/{r['uid']}/approve", json={"approved_by": "alice", "content_hash": current["content_hash"]})
    assert ok.status_code in (200, 409), ok.text
    if ok.status_code == 200:
        a = c.get(f"/requirements/{r['uid']}/approvals").json()
        assert a["current"]["approved_by"] == "alice" and a["current"]["signed_hash"]
        assert [x["status"] for x in c.get(f"/requirements/{r['uid']}/review-requests").json()] == ["approved"]


# --- FEAT-10 ---------------------------------------------------------------------------

def test_mentions_and_review_requests_reach_the_inbox(c):
    r = make_req(c, title="Discussed item")
    c.post(f"/requirements/{r['uid']}/comments", json={"text": "ping @alice and @bob, also me@example.com", "author": "carol"})
    inbox = c.get("/notifications", params={"user": "alice"}).json()
    assert [i["event"] for i in inbox] == ["mention"] and "carol mentioned @alice" in inbox[0]["text"]
    assert c.get("/notifications", params={"user": "example"}).json() == []  # an email address is not a mention
    c.post(f"/requirements/{r['uid']}/review-requests", json={"reviewers": ["alice"], "requested_by": "carol"})
    assert [i["event"] for i in c.get("/notifications", params={"user": "alice"}).json()] == ["review_requested", "mention"]
    assert c.post(f"/notifications/{inbox[0]['id']}/read", params={"user": "alice"}).status_code == 200
    assert len(c.get("/notifications", params={"user": "alice", "unread": True}).json()) == 1


def test_notification_preferences_filter_the_inbox(c):
    r = make_req(c, title="Preferences item")
    assert c.put("/notifications/preferences/alice", json={"events": ["review_requested"]}).status_code == 200
    c.post(f"/requirements/{r['uid']}/comments", json={"text": "hi @alice", "author": "carol"})
    assert c.get("/notifications", params={"user": "alice"}).json() == []
    assert c.put("/notifications/preferences/alice", json={"events": ["nope"]}).status_code == 422
    c.put("/notifications/preferences/alice", json={"muted": True})
    assert c.get("/notifications/preferences/alice").json()["muted"] is True


def test_chat_webhook_bodies():
    from reqtool.features.notifications import chat_body
    body = chat_body("slack", "mention", {"id": "FR-1", "user": "alice", "by": "carol"})
    assert body == {"text": "carol mentioned @alice on FR-1"}
    assert chat_body("json", "mention", {}) is None


# --- FEAT-02 ---------------------------------------------------------------------------

def test_change_set_review_and_merge(c, repo_root):
    a = make_req(c, title="Baseline item")
    seed(repo_root)
    assert c.post("/changesets", json={"name": "../bad"}).status_code == 409
    created = c.post("/changesets", json={"name": "speed-up"})
    assert created.status_code == 201 and created.json()["base"] == "main"
    c.put(f"/requirements/{a['uid']}", json={"title": "Changed in set"})
    make_req(c, title="Added in set")
    git(repo_root, "add", "-A")
    git(repo_root, "commit", "-q", "-m", "set work")
    assert [x["name"] for x in c.get("/changesets").json()] == ["speed-up"]
    d = c.get("/changesets/speed-up/diff").json()
    assert d["summary"] == {"added": 1, "removed": 0, "modified": 1}
    assert c.post("/changesets/speed-up/merge", json={}).status_code == 409  # no reviewer
    m = c.post("/changesets/speed-up/merge", json={"reviewed_by": "dana"})
    assert m.status_code == 200 and m.json()["into"] == "main"
    assert git(repo_root, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert c.get(f"/requirements/{a['uid']}").json()["title"] == "Changed in set"


def test_change_set_refuses_with_uncommitted_changes(c, repo_root):
    seed(repo_root)
    make_req(c, title="Not committed")
    assert c.post("/changesets", json={"name": "x"}).status_code == 409


# --- FEAT-07 ---------------------------------------------------------------------------

def test_snapshot_site_is_static_and_escapes_content(repo_root, tmp_path):
    from reqtool.cli import cli
    cl = TestClient(create_app(repo_root))
    top = make_req(cl, title="<script>alert(1)</script> top")
    low = make_req(cl, title="Child", relationships=[rel(top["uid"])])
    seed(repo_root)
    cl.post("/baselines", json={"name": "v1"})
    make_req(cl, title="Newer item")
    git(repo_root, "add", "-A")
    git(repo_root, "commit", "-q", "-m", "more")
    cl.post("/baselines", json={"name": "v2"})
    out = tmp_path / "site"
    res = CliRunner().invoke(cli, ["snapshot", "--repo", str(repo_root), "--baseline", "v2", "--out", str(out)])
    assert res.exit_code == 0, res.output
    index = (out / "index.html").read_text()
    assert "<script>alert(1)" not in index and "&lt;script&gt;" in index
    assert "Changes since v1" in index and "Newer item" in index
    assert f'href="{top["uid"]}.html"' in (out / f"{low['uid']}.html").read_text()
    z = cl.get("/snapshot.zip", params={"baseline": "v1"})
    assert "index.html" in _names(z)
    assert cl.get("/snapshot.zip", params={"baseline": "nope"}).status_code == 404


# --- ENH-08 / FEAT-08 -------------------------------------------------------------------

def test_module_lifecycle_and_consumers(c, repo_root):
    assert c.post("/modules", json={"id": "brakes", "title": "Brakes"}).status_code == 201
    assert c.post("/modules", json={"id": "brakes"}).status_code == 409
    assert c.post("/modules", json={"id": "../x"}).status_code == 422
    v = c.post("/modules/brakes/version", json={"increment": "minor", "note": "added ABS"}).json()
    assert v["version"] == "1.1.0" and v["history"][-1]["summary"] == "added ABS"
    assert c.post("/modules/brakes/version", json={"increment": "huge"}).status_code == 422
    clone = c.post("/modules/brakes/clone", json={"id": "brakes2"}).json()
    assert clone["id"] == "brakes2" and clone["version"] == "1.0.0" and clone["uid"] != v["uid"]
    assert {m["id"] for m in c.get("/modules").json()} >= {"brakes", "brakes2"}
    c.post("/products", json={"id": "car"})
    store = c.app.state.store
    from reqtool.fileio import load_yaml, save_yaml
    p = load_yaml(repo_root / "products" / "car" / "_product.yaml")
    p["modules"] = [{"id": "brakes"}]
    save_yaml(repo_root / "products" / "car" / "_product.yaml", p)
    store.reload_modules()
    assert c.get("/modules/brakes/consumers").json() == [{"product": "car", "title": "car", "locked_version": None}]
    assert c.get("/modules/nope/consumers").status_code == 404


def test_module_pin_and_update_preview(c, repo_root, monkeypatch, tmp_path):
    from reqtool.features import registry
    from reqtool.fileio import load_yaml, save_yaml
    c.post("/modules", json={"id": "ext"})
    path = repo_root / "modules" / "ext" / "_module.yaml"
    assert c.post("/modules/ext/pin", json={"ref": "v1.2.0"}).status_code == 409  # no remote yet
    m = load_yaml(path)
    m["git_remote"] = "https://example.com/ext.git"
    save_yaml(path, m)
    c.app.state.store.reload_modules()
    assert c.post("/modules/ext/pin", json={"ref": "--upload-pack=x"}).status_code == 409
    assert c.post("/modules/ext/pin", json={"ref": "v1.2.0"}).json()["git_ref"] == "v1.2.0"
    remote = repo_root / "modules" / "ext" / "remote"
    remote.mkdir()
    (remote / "a.yaml").write_text("x: 1\n")
    (remote / "b.yaml").write_text("x: 1\n")

    def fake_clone(url, ref, dest):
        dest.mkdir(parents=True)
        (dest / "a.yaml").write_text("x: 2\n")
        (dest / "c.yaml").write_text("x: 1\n")
    monkeypatch.setattr(registry, "_clone", fake_clone)
    p = c.get("/modules/ext/update-preview", params={"ref": "v2.0.0"}).json()
    assert (p["added"], p["removed"], p["changed"]) == (["c.yaml"], ["b.yaml"], ["a.yaml"])
