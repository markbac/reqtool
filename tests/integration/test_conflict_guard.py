"""DAT-10: an in-progress merge blocks every write route; the check is cheap."""
import subprocess
import time


from reqtool.git_ops import has_conflicts
from tests.conftest import make_req
from tests.integration.test_baseline_diff import _commit_all, _setup


def _git(root, *a):
    return subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True).stdout


def _start_conflicting_merge(root, c, uid):
    _commit_all(root, "base")
    base = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    _git(root, "checkout", "-q", "-b", "other")
    c.put(f"/requirements/{uid}", json={"title": "from other"})
    _commit_all(root, "other change")
    _git(root, "checkout", "-q", base)
    c.app.state.store.load()
    c.put(f"/requirements/{uid}", json={"title": "from main"})
    _commit_all(root, "main change")
    subprocess.run(["git", "merge", "other"], cwd=root, capture_output=True)  # conflicts, leaves MERGE_HEAD


def test_merge_in_progress_blocks_writes_but_not_reads(repo_root):
    c = _setup(repo_root)
    uid = make_req(c, title="T")["uid"]
    _start_conflicting_merge(repo_root, c, uid)
    assert has_conflicts(repo_root)
    writes = [
        ("post", "/requirements", {"title": "x"}),
        ("put", f"/requirements/{uid}", {"title": "y"}),
        ("delete", f"/requirements/{uid}", None),
        ("post", "/principles", {"title": "p"}),
        ("post", "/tbds", {"title": "t"}),
        ("put", "/automation/rules", []),
        ("post", "/baselines", {"name": "b"}),
    ]
    for method, path, body in writes:
        r = getattr(c, method)(path, **({"json": body} if body is not None else {}))
        assert r.status_code == 409, (method, path, r.status_code)
        assert r.json()["detail"]["error"] == "conflict"
    assert c.get("/requirements").status_code == 200
    assert c.get("/health").status_code == 200


def test_clean_tree_and_non_git_dir_do_not_block(repo_root):
    assert not has_conflicts(repo_root)            # not a git repo at all
    c = _setup(repo_root)
    assert c.post("/requirements", json={"title": "ok"}).status_code == 201


def test_aborting_the_merge_unblocks(repo_root):
    c = _setup(repo_root)
    uid = make_req(c, title="T")["uid"]
    _start_conflicting_merge(repo_root, c, uid)
    _git(repo_root, "merge", "--abort")
    assert not has_conflicts(repo_root)
    assert c.post("/requirements", json={"title": "ok"}).status_code == 201


def test_check_is_fast_on_a_large_tree(repo_root):
    _git(repo_root, "init", "-q")
    for i in range(3000):
        (repo_root / "requirements" / f"r{i}.yaml").write_text(f"uid: r{i}\n")
    subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True, capture_output=True)
    has_conflicts(repo_root)  # warm the index
    t = time.perf_counter()
    for _ in range(10):
        has_conflicts(repo_root)
    per_call_ms = (time.perf_counter() - t) / 10 * 1000
    assert per_call_ms < 50, per_call_ms  # generous CI bound; typically a few ms
