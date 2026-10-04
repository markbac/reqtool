"""Regression tests for the defects raised in the code review (SEC-19..24, DAT-18..28, EVT-03, MOD-18..20, QA-08, EXP-01, PKG-02)."""
import datetime
import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from reqtool.api import create_app
from reqtool.auth import UserStore, LoginThrottle, _get_secret_key
from reqtool.fileio import compute_requirement_hash, load_yaml, save_yaml, verify_hash
from tests.conftest import make_req

PW = "correct-horse-battery"


def _git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def secured(repo_root):
    us = UserStore(repo_root)
    us.create_user("alice", PW, role="editor")
    us.create_user("bob", PW, role="editor")
    us.create_user("root", PW, role="admin")
    app = create_app(repo_root, auth_mode="required")
    return TestClient(app, client=("10.0.0.5", 1234))


def _auth(c, name):
    t = c.post("/auth/login", json={"username": name, "password": PW}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


# --- SEC-19 --------------------------------------------------------------------

@pytest.mark.parametrize("filename", ["design.png", "notes.svg", "x.js", "style.css"])
def test_sec19_attachments_need_a_token_whatever_the_extension(secured, filename):
    h = _auth(secured, "alice")
    uid = secured.post("/requirements", json={"title": "r"}, headers=h).json()["uid"]
    up = secured.post(f"/requirements/{uid}/attachments", content=b"secret",
                      headers={**h, "Content-Disposition": f'attachment; filename="{filename}"'})
    assert up.status_code == 201
    anon = TestClient(secured.app, client=("10.0.0.5", 1234))
    assert anon.get(f"/requirements/{uid}/attachments/{filename}").status_code == 401
    assert anon.get(f"/artefacts/{uid}/attachments/{filename}").status_code == 401
    assert secured.get(f"/requirements/{uid}/attachments/{filename}", headers=h).content == b"secret"


def test_sec19_top_level_ui_files_stay_public():
    from reqtool.security import is_public_path
    assert is_public_path("GET", "/favicon.ico")
    assert is_public_path("GET", "/assets/index-abc.js")
    assert not is_public_path("GET", "/requirements/u/attachments/a.png")


# --- SEC-20 --------------------------------------------------------------------

def test_sec20_local_mode_refuses_foreign_host_and_cross_site_writes(repo_root):
    c = TestClient(create_app(repo_root, auth_mode="local"), client=("127.0.0.1", 5000))
    assert c.get("/requirements", headers={"Host": "evil.example.com:8765"}).status_code == 403
    assert c.get("/requirements", headers={"Host": "localhost:8765"}).status_code == 200
    assert c.get("/requirements", headers={"Host": "127.0.0.1:8765"}).status_code == 200
    assert c.get("/requirements", headers={"Host": "[::1]:8765"}).status_code == 200
    uid = make_req(c)["uid"]
    evil = {"Origin": "https://evil.example"}
    assert c.post(f"/requirements/{uid}/clone", headers=evil).status_code == 403
    assert c.post("/requirements", content=json.dumps({"title": "x"}),
                  headers={**evil, "Content-Type": "text/plain"}).status_code == 403
    # Reading across origins is governed by CORS, and a same-machine page may write.
    assert c.get("/requirements", headers=evil).status_code == 200
    assert c.post(f"/requirements/{uid}/clone", headers={"Origin": "http://localhost:5173"}).status_code == 201


def test_sec20_extra_hosts_can_be_allowed(repo_root, monkeypatch):
    monkeypatch.setenv("REQTOOL_ALLOWED_HOSTS", "reqs.internal")
    c = TestClient(create_app(repo_root, auth_mode="local"), client=("127.0.0.1", 5000))
    assert c.get("/requirements", headers={"Host": "reqs.internal:80"}).status_code == 200


# --- SEC-21 --------------------------------------------------------------------

@pytest.mark.parametrize("content", [b"", b"short"])
def test_sec21_invalid_secret_key_is_regenerated(repo_root, content):
    key_file = repo_root / ".reqtool" / ".secret_key"
    key_file.write_bytes(content)
    key = _get_secret_key(repo_root)
    assert len(key) >= 32
    assert key_file.read_bytes() == key
    assert _get_secret_key(repo_root) == key  # stable once valid


def test_sec21_login_survives_an_empty_key_file(repo_root):
    UserStore(repo_root).create_user("root", PW, role="admin")
    c = TestClient(create_app(repo_root, auth_mode="required"), client=("10.0.0.5", 1))
    assert c.post("/auth/login", json={"username": "root", "password": PW}).status_code == 200
    (repo_root / ".reqtool" / ".secret_key").write_bytes(b"")
    assert c.post("/auth/login", json={"username": "root", "password": PW}).status_code == 200


# --- SEC-22 --------------------------------------------------------------------

def test_sec22_history_records_the_logged_in_user(secured):
    h = _auth(secured, "alice")
    uid = secured.post("/requirements", json={"title": "x"}, headers=h).json()["uid"]
    secured.put(f"/requirements/{uid}", json={"title": "y"}, headers=h)
    hist = secured.get(f"/requirements/{uid}", headers=h).json()["history"]
    assert {e["modified_by"] for e in hist} == {"alice"}


def test_sec22_comment_author_comes_from_the_login_and_ownership_is_enforced(secured):
    ha, hb, hr = _auth(secured, "alice"), _auth(secured, "bob"), _auth(secured, "root")
    uid = secured.post("/requirements", json={"title": "x"}, headers=ha).json()["uid"]
    cm = secured.post(f"/requirements/{uid}/comments", json={"text": "hi", "author": "bob"}, headers=ha).json()
    assert cm["author"] == "alice"
    url = f"/requirements/{uid}/comments/{cm['uid']}"
    assert secured.put(url, json={"text": "edited"}, headers=hb).status_code == 403
    assert secured.delete(url, headers=hb).status_code == 403
    assert secured.put(url, json={"text": "mine"}, headers=ha).status_code == 200
    assert secured.delete(url, headers=hr).status_code == 200  # an administrator may moderate


def test_sec22_attachment_author_is_the_login(secured):
    h = _auth(secured, "alice")
    uid = secured.post("/requirements", json={"title": "x"}, headers=h).json()["uid"]
    up = secured.post(f"/requirements/{uid}/attachments?author=bob", content=b"d",
                      headers={**h, "Content-Disposition": 'attachment; filename="a.txt"'})
    assert up.json()["added_by"] == "alice"


# --- SEC-23 --------------------------------------------------------------------

def test_sec23_throttle_table_is_bounded():
    t = LoginThrottle()
    t.MAX_KEYS = 100
    for i in range(1000):
        t.record_failure(f"user{i}")
    assert len(t._fails) <= 101


def test_sec23_unknown_user_still_pays_for_a_hash(repo_root, monkeypatch):
    import reqtool.auth as auth
    calls = []
    real = auth.verify_password
    monkeypatch.setattr(auth, "verify_password", lambda *a, **k: calls.append(1) or real(*a, **k))
    assert UserStore(repo_root).authenticate("nobody", "x") is None
    assert calls, "no password hash was computed for an unknown user"


# --- SEC-24 / EXP-01 -----------------------------------------------------------

def test_sec24_csv_cells_that_look_like_formulas_are_neutralised(client):
    make_req(client, title='=HYPERLINK("http://evil.example","x")')
    make_req(client, title="@SUM(A1)")
    make_req(client, title="-1+1")
    make_req(client, title="plain")
    body = client.post("/export/csv", json={}).content.decode("utf-8")
    assert "'=HYPERLINK" in body and "'@SUM" in body and "'-1+1" in body
    assert "plain" in body


def test_exp01_csv_relationships_use_full_uids(client):
    a = make_req(client, title="A")["uid"]
    b = make_req(client, title="B")["uid"]
    client.put(f"/requirements/{a}", json={"relationships": [{"type": "refines", "target": {"uid": b}}]})
    body = client.post("/export/csv", json={"fields": ["id", "relationships"]}).content.decode("utf-8")
    assert b in body


def test_exp01_reqif_declares_types_and_relations(client):
    from reqtool import __version__
    a = make_req(client, title="A")["uid"]
    b = make_req(client, title="B")["uid"]
    client.put(f"/requirements/{a}", json={"relationships": [{"type": "refines", "target": {"uid": b}}]})
    xml = client.get("/export/reqif").text
    assert f"reqtool-{__version__}" in xml
    for tag in ("<DATATYPES>", "<SPEC-TYPES>", "<SPEC-RELATIONS>", "<SPEC-RELATION ", "SPEC-OBJECT-TYPE"):
        assert tag in xml, tag
    from reqtool.exports import parse_reqif_xml
    assert {o["title"] for o in parse_reqif_xml(xml)["spec_objects"]} == {"A", "B"}


# --- DAT-18 --------------------------------------------------------------------

def test_dat18_unquoted_yaml_date_hashes_like_the_quoted_string():
    quoted = compute_requirement_hash({"id": "X", "planned_start_date": "2026-10-01"})
    assert compute_requirement_hash({"id": "X", "planned_start_date": datetime.date(2026, 10, 1)}) == quoted


def test_dat18_hand_edited_date_does_not_break_the_repository(repo_root):
    c = TestClient(create_app(repo_root))
    uid = make_req(c)["uid"]
    path = repo_root / "requirements" / f"{uid}.yaml"
    import re
    text = re.sub(r"^planned_start_date:.*$", "planned_start_date: 2026-10-01", path.read_text(), flags=re.M)
    assert "planned_start_date: 2026-10-01" in text
    path.write_text(text)
    c2 = TestClient(create_app(repo_root))
    assert c2.get(f"/requirements/{uid}").json()["planned_start_date"] == "2026-10-01"
    assert c2.put(f"/requirements/{uid}", json={"title": "ok"}).status_code == 200
    assert c2.get("/validate").status_code == 200


# --- DAT-19 / DAT-20 -----------------------------------------------------------

SAFETY = {"asil_level": "ASIL_D", "dal_level": "A", "safety_standard": "ISO 26262", "target_release": "1.0",
          "planned_start_date": "2026-11-01", "source_document": "SRS-1 cl.4", "mitigates_hazard": "H-1"}


def test_dat19_create_keeps_safety_and_planning_fields(client):
    d = client.post("/requirements", json={"title": "s", **SAFETY}).json()
    for k, v in SAFETY.items():
        assert d[k] == v, k
    assert client.get(f"/requirements/{d['uid']}").json()["asil_level"] == "ASIL_D"


def test_dat19_update_keeps_safety_and_planning_fields(client):
    uid = make_req(client)["uid"]
    r = client.put(f"/requirements/{uid}", json={"asil_level": "ASIL_B", "target_release": "2.0"}).json()
    assert r["asil_level"] == "ASIL_B" and r["target_release"] == "2.0"


def test_dat19_clone_keeps_safety_fields(client):
    uid = client.post("/requirements", json={"title": "s", **SAFETY}).json()["uid"]
    assert client.post(f"/requirements/{uid}/clone").json()["asil_level"] == "ASIL_D"


def test_dat20_put_null_clears_a_field_but_omitted_fields_stay(client):
    uid = make_req(client)["uid"]
    client.put(f"/requirements/{uid}", json={"owner": "alice", "assignee": "bob"})
    r = client.put(f"/requirements/{uid}", json={"owner": None}).json()
    assert r["owner"] is None and r["assignee"] == "bob"


def test_dat20_put_null_moves_an_item_to_the_root(client):
    parent = make_req(client, title="p")["uid"]
    child = client.post("/requirements", json={"title": "c", "parentId": parent}).json()["uid"]
    assert client.put(f"/requirements/{child}", json={"parentId": None}).json()["parentId"] is None


def test_dat20_null_does_not_wipe_required_fields(client):
    uid = make_req(client, title="keep")["uid"]
    r = client.put(f"/requirements/{uid}", json={"title": None, "status": None, "content": None}).json()
    assert r["title"] == "keep" and r["status"] and isinstance(r["content"], dict)


# --- DAT-21 --------------------------------------------------------------------

@pytest.mark.parametrize("field", ["history", "version", "content_hash", "deleted", "created", "uid"])
def test_dat21_bulk_rejects_protected_fields(client, field):
    uid = make_req(client)["uid"]
    r = client.post("/requirements/bulk", json={"uids": [uid], "fields": {field: "x"}})
    assert r.status_code == 422
    assert client.get(f"/requirements/{uid}").json()["uid"] == uid


def test_dat21_bulk_still_updates_ordinary_fields(client):
    uid = make_req(client)["uid"]
    r = client.post("/requirements/bulk", json={"uids": [uid], "fields": {"owner": "x", "priority": "high"}})
    assert r.status_code == 200 and r.json()["count"] == 1


# --- DAT-22 --------------------------------------------------------------------

def test_dat22_superseded_decision_still_verifies(client):
    a = client.post("/decisions", json={"title": "A"}).json()
    b = client.post("/decisions", json={"title": "B", "supersedes": a["uid"]}).json()
    old = client.app.state.store.get_decision(a["uid"])
    assert old["status"] == "superseded" and old["superseded_by"] == b["uid"]
    assert verify_hash(old, "tbd")
    assert len(old["history"]) == 2 and "Superseded" in old["history"][-1]["summary"]


# --- DAT-23 --------------------------------------------------------------------

def _seed_git(root):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed", "--allow-empty")


def test_dat23_empty_commit_message_is_rejected_before_anything_changes(repo_root):
    c = TestClient(create_app(repo_root))
    uid = make_req(c)["uid"]
    _seed_git(repo_root)
    before = c.get(f"/requirements/{uid}").json()
    r = c.post(f"/requirements/{uid}/commit", json={"message": "  "})
    assert r.status_code == 422
    assert c.get(f"/requirements/{uid}").json() == before
    assert _git(repo_root, "status", "--porcelain") == ""


def test_dat23_failed_git_commit_rolls_the_item_back(repo_root, monkeypatch):
    import reqtool.routers.requirements as rr
    c = TestClient(create_app(repo_root))
    uid = make_req(c)["uid"]
    _seed_git(repo_root)
    before = c.get(f"/requirements/{uid}").json()

    def boom(*a, **k):
        raise RuntimeError("git commit failed: simulated")
    monkeypatch.setattr(rr, "git_commit", boom)
    assert c.post(f"/requirements/{uid}/commit", json={"message": "m"}).status_code == 500
    assert c.get(f"/requirements/{uid}").json() == before
    assert _git(repo_root, "status", "--porcelain") == ""


def test_dat23_decision_commit_leaves_the_tree_clean(repo_root):
    c = TestClient(create_app(repo_root))
    d = c.post("/decisions", json={"title": "C"}).json()
    _seed_git(repo_root)
    r = c.post(f"/decisions/{d['uid']}/commit", json={"message": "commit decision"})
    assert r.status_code == 200, r.text
    assert _git(repo_root, "status", "--porcelain") == ""


# --- DAT-24 / DAT-25 -----------------------------------------------------------

def test_dat24_checkout_of_an_older_file_is_reloaded(repo_root):
    c = TestClient(create_app(repo_root))
    uid = make_req(c, title="orig")["uid"]
    _seed_git(repo_root)
    c.put(f"/requirements/{uid}", json={"title": "newer"})
    store = c.app.state.store
    path = repo_root / "requirements" / f"{uid}.yaml"
    _git(repo_root, "checkout", "--", str(path.relative_to(repo_root)))
    store.reload_file(path)
    assert store.requirements[uid]["title"] == "orig"


def test_dat25_file_named_differently_from_its_uid_is_saved_in_place(repo_root):
    c = TestClient(create_app(repo_root))
    uid = make_req(c, title="orig")["uid"]
    (repo_root / "requirements" / f"{uid}.yaml").rename(repo_root / "requirements" / "REQ-001.yaml")
    c2 = TestClient(create_app(repo_root))
    assert c2.put(f"/requirements/{uid}", json={"title": "edited"}).status_code == 200
    assert sorted(p.name for p in (repo_root / "requirements").glob("*.yaml")) == ["REQ-001.yaml"]
    assert TestClient(create_app(repo_root)).get(f"/requirements/{uid}").json()["title"] == "edited"


# --- DAT-26 / DAT-27 -----------------------------------------------------------

def test_dat26_clone_copies_attachment_files(client):
    uid = make_req(client)["uid"]
    client.post(f"/requirements/{uid}/attachments", content=b"payload",
                headers={"Content-Disposition": 'attachment; filename="spec.txt"'})
    clone = client.post(f"/requirements/{uid}/clone").json()
    got = client.get(f"/requirements/{clone['uid']}/attachments/spec.txt")
    assert got.status_code == 200 and got.content == b"payload"


def test_dat27_unknown_parent_is_rejected(client):
    assert client.post("/requirements", json={"title": "x", "parentId": "does-not-exist"}).status_code == 422
    uid = make_req(client)["uid"]
    assert client.put(f"/requirements/{uid}", json={"parentId": "nope"}).status_code == 422


def test_dat27_children_of_a_deleted_parent_move_up_a_level(client):
    grand = make_req(client, title="g")["uid"]
    parent = client.post("/requirements", json={"title": "p", "parentId": grand}).json()["uid"]
    child = client.post("/requirements", json={"title": "c", "parentId": parent}).json()["uid"]
    assert client.delete(f"/requirements/{parent}").status_code == 200
    assert client.get(f"/requirements/{child}").json()["parentId"] == grand
    flat = json.dumps(client.app.state.store.build_tree())
    assert child in flat


# --- DAT-28 --------------------------------------------------------------------

def test_dat28_counts_exports_and_search_separate_decisions_from_tbds(client):
    client.post("/decisions", json={"title": "Use Postgres"})
    client.post("/tbds", json={"title": "Which broker"})
    info = client.get("/repo").json()
    assert info["tbds_count"] == 1 and info["decisions_count"] == 1
    totals = client.get("/metrics").json()["totals"]
    assert totals["tbds"] == 1
    adr = client.get("/export/adr").text
    assert "Use Postgres" in adr and "Which broker" not in adr
    found = {r["title"]: r["type"] for r in client.get("/search", params={"q": "Postgres"}).json()}
    assert found.get("Use Postgres") == "decision"


# --- EVT-03 --------------------------------------------------------------------

def test_evt03_reload_of_a_path_outside_the_repo_is_ignored(store, tmp_path_factory):
    outside = tmp_path_factory.mktemp("elsewhere") / "requirements" / "x.yaml"
    store.reload_file(outside)  # used to raise ValueError


def test_evt03_config_detection_uses_the_path_not_a_substring(tmp_path):
    from reqtool.store import Store
    root = tmp_path / "my.reqtool-repo"
    for d in ("requirements", "principles", "decisions", ".reqtool"):
        (root / d).mkdir(parents=True)
    s = Store(root)
    s.load()
    calls = []
    s.load = lambda: calls.append(1)
    s.reload_file(root / "requirements" / "missing.yaml")
    assert not calls


def test_evt03_handler_exceptions_do_not_escape(store):
    from reqtool.watcher import make_handler

    class Event:
        is_directory = False
        src_path = "/x/requirements/a.yaml"
    store.reload_file = lambda p: (_ for _ in ()).throw(ValueError("boom"))
    make_handler(store).on_any_event(Event())  # must not raise


# --- MOD-18..20, QA-08, ENH-10, PKG-02 ----------------------------------------

def test_mod18_metrics_tolerates_empty_yaml_blocks(repo_root):
    c = TestClient(create_app(repo_root))
    uid = make_req(c)["uid"]
    path = repo_root / "requirements" / f"{uid}.yaml"
    data = load_yaml(path)
    data["verification"] = None
    data["content"] = None
    save_yaml(path, data)
    assert TestClient(create_app(repo_root)).get("/metrics").status_code == 200


def test_mod19_matrix_is_per_product_and_new_products_are_stamped(client):
    from reqtool import __version__
    make_req(client, title="r1")
    assert client.get("/products/unknown/matrix").status_code == 404
    p = client.post("/products", json={"id": "prod-a"}).json()
    assert p["tool_version"] == __version__ and p["content_hash"].startswith("sha256:")
    assert client.get("/products/prod-a/matrix").status_code == 200


def test_mod20_import_of_a_missing_module_is_a_404(client):
    client.post("/products", json={"id": "prod-a"})
    store = client.app.state.store
    store.products["prod-a"]["modules"] = [{"id": "ghost"}]
    assert client.post("/modules/ghost/import").status_code == 404


@pytest.mark.parametrize("body", [{"text": None}, {"text": 5}, {"text": ["x"]}, {}])
def test_qa08_bad_comment_bodies_are_422_not_500(client, body):
    uid = make_req(client)["uid"]
    assert client.post(f"/requirements/{uid}/comments", json=body).status_code == 422


@pytest.mark.parametrize("path", ["impact", "progress", "rollup", "history"])
def test_enh10_human_ids_work_on_every_requirement_route(client, path):
    r = make_req(client, title="h")
    assert client.get(f"/requirements/{r['uid']}/{path}").status_code == client.get(f"/requirements/{r['id']}/{path}").status_code == 200


def test_pkg02_git_runs_with_utf8_and_a_committer(repo_root):
    c = TestClient(create_app(repo_root))
    uid = make_req(c, title="Größe")["uid"]
    _seed_git(repo_root)
    c.put(f"/requirements/{uid}", json={"title": "Größe 2"})
    r = c.post(f"/requirements/{uid}/commit", json={"message": "änderung – ✓"})
    assert r.status_code == 200, r.text
    assert _git(repo_root, "log", "-1", "--pretty=%B") == "änderung – ✓"
    assert _git(repo_root, "log", "-1", "--pretty=%cn") == "Requirements Tool"


# --- Phase 2: DAT-05, DAT-06, DAT-13, PERF-01, PERF-02, PERF-04 -----------------

def test_dat05_getters_return_copies(store):
    r = store.create_requirement({"title": "x"})
    got = store.get_requirement(r["uid"])
    got["title"] = "tampered"
    got["history"].clear()
    assert store.requirements[r["uid"]]["title"] == "x"
    assert store.requirements[r["uid"]]["history"]
    p = store.create_principle({"title": "p"})
    store.get_principle(p["uid"])["title"] = "tampered"
    assert store.principles[p["uid"]]["title"] == "p"
    d = store.create_decision({"title": "d"})
    store.get_decision(d["uid"])["title"] = "tampered"
    assert store.decisions[d["uid"]]["title"] == "d"


def test_dat06_deleting_a_tbd_or_decision_file_removes_it_incrementally(store):
    tbd = store.create_tbd({"title": "t"})
    dec = store.create_decision({"title": "d"})
    for item in (tbd, dec):
        path = store.decision_path(item["uid"])
        path.unlink()
        store.reload_file(path)
        assert item["uid"] not in store.decisions


def test_dat06_legacy_tbds_folder_files_load_and_delete(store):
    legacy = store.root / "tbds"
    legacy.mkdir()
    store.create_tbd({"title": "t"})
    uid = next(iter(store.decisions))
    src = store.decision_path(uid)
    moved = legacy / src.name
    src.rename(moved)
    store.load()
    assert uid in store.decisions and store.decision_path(uid) == moved
    moved.unlink()
    store.reload_file(moved)
    assert uid not in store.decisions


def test_dat06_collections_exist_before_load(tmp_path):
    from reqtool.store import Store
    s = Store(tmp_path)
    assert s.decisions == {} and s.requirements == {}


def test_dat13_cli_edit_is_seen_by_a_running_server_after_a_reload(repo_root):
    from click.testing import CliRunner
    from reqtool.cli import cli
    c = TestClient(create_app(repo_root))
    uid = make_req(c, title="before")["uid"]
    path = repo_root / "requirements" / f"{uid}.yaml"
    data = load_yaml(path)
    data["title"] = "after (CLI)"  # what an offline CLI write leaves behind, last_modified untouched
    save_yaml(path, data)
    c.app.state.store.reload_file(path)
    assert c.get(f"/requirements/{uid}").json()["title"] == "after (CLI)"
    assert CliRunner().invoke(cli, ["--help"]).exit_code == 0


def test_perf01_graph_matches_the_scan_and_is_fast_on_10k_items(store):
    import time
    n = 10_000
    chain = {}
    for i in range(n):
        uid = f"u{i:05d}"
        chain[uid] = {"uid": uid, "id": f"R{i}", "title": "t", "status": "draft", "req_type": "functional",
                      "parentId": f"u{(i - 1) // 2:05d}" if i else None,
                      "relationships": [{"type": "derived_from", "target": {"uid": f"u{i - 1:05d}"}}] if i else []}
    store.requirements = chain
    store._revision += 1
    t = time.perf_counter()
    store.compute_impact("u00000")  # builds the graph once
    first = time.perf_counter() - t
    t = time.perf_counter()
    for _ in range(20):
        impact = store.compute_impact("u00100")
        store.compute_progress_rollup("u00001")
    warm = (time.perf_counter() - t) / 20
    assert impact["downstream_count"] == n - 101  # the chain below u00100
    assert first < 5 and warm < 0.25, (first, warm)


def test_perf02_duplicate_detection_matches_brute_force_and_scales(store):
    import random
    import re
    import time
    from reqtool.intelligence import detect_duplicate_requirements
    rnd = random.Random(7)
    vocab = [f"word{i}" for i in range(40)]

    def req(k, lo, hi):
        return {"uid": f"u{k}", "id": f"R{k}", "title": " ".join(rnd.choices(vocab, k=rnd.randint(2, 4))),
                "content": {"description": " ".join(rnd.choices(vocab, k=rnd.randint(lo, hi)))}}
    store.requirements = {f"u{k}": req(k, 3, 10) for k in range(200)}
    store._revision += 1
    tok = lambda r: {w for w in re.findall(r"\w+", f"{r['title']} {r['content']['description']}".lower()) if len(w) > 3}
    items = list(store.requirements.values())
    for threshold in (0.25, 0.5):
        expected = set()
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = tok(items[i]), tok(items[j])
                if a and b and len(a & b) / len(a | b) >= threshold:
                    expected.add(frozenset((items[i]["uid"], items[j]["uid"])))
        got = {frozenset((d["req_a"]["uid"], d["req_b"]["uid"])) for d in detect_duplicate_requirements(store, threshold)}
        assert got == expected
    words = [f"term{i}" for i in range(4000)]
    store.requirements = {f"v{k}": {"uid": f"v{k}", "id": f"R{k}", "title": " ".join(rnd.choices(words, k=4)),
                                    "content": {"description": " ".join(rnd.choices(words, k=15))}} for k in range(3000)}
    store._revision += 1
    t = time.perf_counter()
    detect_duplicate_requirements(store, 0.5)
    assert time.perf_counter() - t < 5  # was ~34 s for 2,000 items


def test_perf04_resolved_set_is_cached_until_a_write(store):
    store.create_requirement({"title": "a"})
    first = store.resolved_requirements()
    assert store.resolved_requirements() is first
    store.create_requirement({"title": "b"})
    second = store.resolved_requirements()
    assert second is not first and len(second) == 2


# --- ARC-12 / ARC-07 / ARC-08 ----------------------------------------------------

def test_arc12_watcher_is_a_parameter_not_a_guess_about_pytest(repo_root):
    import time
    assert create_app(repo_root).state.watcher is None  # REQTOOL_WATCHER=0 in the test environment
    app = create_app(repo_root, enable_watcher=True)
    try:
        assert app.state.watcher is not None
        uid = app.state.store.create_requirement({"title": "x"})["uid"]
        path = repo_root / "requirements" / f"{uid}.yaml"
        data = load_yaml(path)
        data["title"] = "edited outside"
        save_yaml(path, data)
        for _ in range(50):
            if app.state.store.requirements[uid]["title"] == "edited outside":
                break
            time.sleep(0.1)
        assert app.state.store.requirements[uid]["title"] == "edited outside"
    finally:
        from reqtool.watcher import stop_watcher
        stop_watcher(app.state.watcher)


def test_arc07_no_import_cycle_between_cli_and_api(tmp_path):
    out = subprocess.run(
        [__import__("sys").executable, "-c",
         "import sys; import reqtool.api; assert 'reqtool.cli' not in sys.modules, 'api pulled in the CLI'"],
        capture_output=True, text=True, env={**__import__("os").environ, "PYTHONPATH": "src"})
    assert out.returncode == 0, out.stderr


def test_arc08_public_artefact_api(store):
    r = store.create_requirement({"title": "x"})
    assert store.has_artefact(r["uid"]) and not store.has_artefact("nope")
    got, kind = store.get_artefact(r["uid"])
    got["title"] = "tampered"
    assert kind == "requirement" and store.requirements[r["uid"]]["title"] == "x"
    assert store.update_artefact(r["uid"], {"title": "y"}, summary="s")["title"] == "y"
