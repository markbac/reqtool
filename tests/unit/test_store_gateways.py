"""ARC-04: the store reaches files and git only through a Storage and a Vcs, so its rules run with neither."""

import ast
from pathlib import Path

import pytest

from reqtool.storage import FileStorage, MemoryStorage
from reqtool.store import Store
from reqtool.vcs import NullVcs

ROOT = Path("/memory-repo")
SRC = Path(__file__).resolve().parents[2] / "src" / "reqtool"


def memory_store(files=None, vcs=None):
    storage = MemoryStorage(files)
    store = Store(ROOT, storage=storage, vcs=vcs or NullVcs())
    store.load()
    return store, storage


def test_a_store_runs_with_no_file_system():
    store, storage = memory_store()
    made = store.create_requirement({"title": "In memory", "content": {"description": "The system shall exist."}})
    assert made["id"] == "FR-001" or made["id"].endswith("001")
    assert storage.exists(ROOT / "requirements" / f"{made['uid']}.yaml")
    assert not ROOT.exists(), "nothing may reach the real disk"


def test_updates_and_history_work_in_memory():
    store, storage = memory_store()
    made = store.create_requirement({"title": "First"})
    store.update_requirement(made["uid"], {"title": "Second"}, summary="rename")
    stored = storage.read(ROOT / "requirements" / f"{made['uid']}.yaml")
    assert stored["title"] == "Second" and stored["version"] != "1.0.0"
    assert len(stored["history"]) == 2


def test_load_reads_what_the_storage_holds():
    first, storage = memory_store()
    made = first.create_requirement({"title": "Persisted"})
    second = Store(ROOT, storage=storage, vcs=NullVcs())
    second.load()
    assert second.requirement_map()[made["uid"]]["title"] == "Persisted"


def test_a_product_and_module_can_be_locked_with_no_git():
    store, storage = memory_store({
        ROOT / "products" / "p1" / "_product.yaml": {"id": "p1", "title": "P", "modules": [{"id": "m1"}]},
        ROOT / "modules" / "m1" / "_module.yaml": {"id": "m1", "title": "M", "version": "2.0.0"},
        ROOT / "modules" / "m1" / "a.yaml": {"uid": "u1", "id": "M-1", "title": "a"},
    }, vcs=NullVcs(commit="c0ffee"))
    lock = store.import_module("p1", "m1")
    entry = lock["locked"][0]
    assert entry["sha"] == "c0ffee" and entry["version"] == "2.0.0" and entry["content_hash"].startswith("sha256:")
    assert store.verify_module("p1", "m1")["verified"] is True
    storage.write(ROOT / "modules" / "m1" / "a.yaml", {"uid": "u1", "id": "M-1", "title": "changed"})
    assert store.verify_module("p1", "m1")["verified"] is False


def test_fetching_a_remote_module_asks_the_vcs_and_pins_the_commit():
    vcs = NullVcs(commit="abc123")
    store, storage = memory_store({
        ROOT / "modules" / "m1" / "_module.yaml": {"id": "m1", "title": "M", "git_remote": "https://example.com/m.git",
                                                   "git_ref": "main"},
    }, vcs=vcs)
    result = store.fetch_remote_module("m1")
    assert vcs.fetches == [("https://example.com/m.git", "main", ROOT / "modules" / "m1" / "remote")]
    assert result["commit"] == "abc123"
    assert storage.read(ROOT / "modules" / "m1" / "_module.yaml")["pinned_commit"] == "abc123"


def test_an_unsafe_remote_is_refused_before_the_vcs_is_asked():
    vcs = NullVcs()
    store, _ = memory_store({
        ROOT / "modules" / "m1" / "_module.yaml": {"id": "m1", "git_remote": "--upload-pack=evil", "git_ref": "main"},
    }, vcs=vcs)
    with pytest.raises(ValueError):
        store.fetch_remote_module("m1")
    assert vcs.fetches == []


def test_file_storage_lists_in_order_and_survives_a_missing_directory(tmp_path):
    fs = FileStorage()
    assert fs.list_yaml(tmp_path / "none") == [] and fs.list_dirs(tmp_path / "none") == []
    (tmp_path / "b.yaml").write_text("a: 1\n")
    (tmp_path / "a.yaml").write_text("a: 1\n")
    (tmp_path / "x.txt").write_text("")
    (tmp_path / "d").mkdir()
    assert [p.name for p in fs.list_yaml(tmp_path)] == ["a.yaml", "b.yaml"]
    assert [p.name for p in fs.list_dirs(tmp_path)] == ["d"]


def test_memory_storage_lists_directories_from_the_files_under_them():
    ms = MemoryStorage({Path("/r/modules/a/_module.yaml"): {}, Path("/r/modules/b/x.yaml"): {}, Path("/r/modules/c.yaml"): {}})
    assert ms.list_dirs(Path("/r/modules")) == [Path("/r/modules/a"), Path("/r/modules/b")]
    assert ms.list_yaml(Path("/r/modules")) == [Path("/r/modules/c.yaml")]


def test_the_store_does_not_touch_git_or_the_file_system_itself():
    """No subprocess, git_ops, save_yaml/load_yaml or path-walking inside store.py and store_parts/."""
    banned_names = {"save_yaml", "load_yaml", "run_git", "_git_remote"}
    banned_attrs = {"mkdir", "unlink", "iterdir", "glob", "rglob", "read_text", "write_text", "read_bytes", "exists"}
    offenders = []
    files = [SRC / "store.py", *sorted((SRC / "store_parts").glob("*.py"))]
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Name) and node.id in banned_names:
                offenders.append(f"{path.name}:{node.lineno} {node.id}")
            if isinstance(node, ast.Attribute) and node.attr in banned_attrs and not (
                    isinstance(node.value, ast.Attribute) and node.value.attr == "storage"):
                offenders.append(f"{path.name}:{node.lineno} .{node.attr}")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] + [getattr(node, "module", "") or ""]
                if any(n in {"subprocess", "reqtool.git_ops", "git_ops", "shutil"} for n in names):
                    offenders.append(f"{path.name}:{node.lineno} import")
    assert not offenders, "infrastructure inside the store:\n" + "\n".join(offenders)
