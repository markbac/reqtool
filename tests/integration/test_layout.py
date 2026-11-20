"""#380: requirements live in requirements/ (modules in requirements/modules/<id>/), work items and issues in work/."""
import subprocess

from reqtool.commands.migrate import migrate_layout
from reqtool.store import Store
from reqtool.validation import validate_all


def _store(root):
    s = Store(root)
    s.load()
    return s


def test_new_items_go_to_the_folder_of_their_family(repo_root):
    store = _store(repo_root)
    req = store.create_requirement({"title": "R", "req_type": "functional"})
    story = store.create_requirement({"title": "S", "req_type": "story"})
    issue = store.create_requirement({"title": "I", "req_type": "issue"})
    assert (repo_root / "requirements" / f"{req['uid']}.yaml").exists()
    assert (repo_root / "work" / f"{story['uid']}.yaml").exists()
    assert (repo_root / "work" / f"{issue['uid']}.yaml").exists()
    # Both folders load into the one collection.
    again = _store(repo_root)
    assert {req["uid"], story["uid"], issue["uid"]} <= set(again.requirement_map())


def test_changing_the_type_to_the_other_family_moves_the_file(repo_root):
    store = _store(repo_root)
    item = store.create_requirement({"title": "Was a story", "req_type": "story"})
    store.update_requirement(item["uid"], {"req_type": "functional"})
    assert (repo_root / "requirements" / f"{item['uid']}.yaml").exists()
    assert not (repo_root / "work" / f"{item['uid']}.yaml").exists()
    assert _store(repo_root).requirement_map()[item["uid"]]["req_type"] == "functional"


def test_a_type_can_choose_its_family_in_hierarchy_yaml(repo_root):
    store = _store(repo_root)
    store.hierarchy.types["functional"].family = "work"
    item = store.create_requirement({"title": "R", "req_type": "functional"})
    assert (repo_root / "work" / f"{item['uid']}.yaml").exists()


def test_an_unmigrated_repository_loads_and_warns(repo_root):
    store = _store(repo_root)
    story = store.create_requirement({"title": "S", "req_type": "story"})
    (repo_root / "work" / f"{story['uid']}.yaml").rename(repo_root / "requirements" / f"{story['uid']}.yaml")
    old = _store(repo_root)
    assert story["uid"] in old.requirement_map()
    warnings = [w for w in validate_all(old)["warnings"] if w["code"] == "misplaced_file"]
    assert [w["uid"] for w in warnings] == [story["uid"]] and "req migrate" in warnings[0]["message"]


def test_migration_moves_work_items_and_modules_with_git_history_and_is_idempotent(repo_root):
    store = _store(repo_root)
    story = store.create_requirement({"title": "S", "req_type": "story"})
    req = store.create_requirement({"title": "R", "req_type": "functional"})
    (repo_root / "work" / f"{story['uid']}.yaml").rename(repo_root / "requirements" / f"{story['uid']}.yaml")
    legacy = repo_root / "modules" / "core"
    legacy.mkdir(parents=True)
    (legacy / "_module.yaml").write_text("id: core\ntitle: Core\nversion: 1.0.0\n")
    (repo_root / ".gitattributes").write_text("requirements/*.yaml merge=reqtool\n")
    git = lambda *a: subprocess.run(["git", *a], cwd=repo_root, check=True, capture_output=True, text=True).stdout  # noqa: E731
    git("init", "-q")
    git("add", "-A")
    git("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "old layout")

    assert _store(repo_root).module_map().keys() == {"core"}          # legacy modules/ still loads
    assert migrate_layout(repo_root) == {"work": 1, "modules": 1, "skipped_modules": []}
    assert migrate_layout(repo_root) == {"work": 0, "modules": 0, "skipped_modules": []}

    assert (repo_root / "work" / f"{story['uid']}.yaml").exists()
    assert (repo_root / "requirements" / f"{req['uid']}.yaml").exists()
    assert (repo_root / "requirements" / "modules" / "core" / "_module.yaml").exists()
    assert not (repo_root / "modules").exists()
    assert "R  requirements/" in git("status", "--porcelain")                # recorded as renames
    assert "work/*.yaml merge=reqtool" in (repo_root / ".gitattributes").read_text()
    after = _store(repo_root)
    assert after.module_map().keys() == {"core"} and not after.misplaced_items()


def test_new_modules_are_created_under_requirements_modules(client, repo_root):
    r = client.post("/modules", json={"id": "brakes", "title": "Brakes"})
    assert r.status_code == 201, r.text
    assert (repo_root / "requirements" / "modules" / "brakes" / "_module.yaml").exists()
    assert not (repo_root / "modules").exists()
