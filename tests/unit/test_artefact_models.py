"""ARC-06: the typed models describe what the store really holds, so they cannot drift from it."""

from reqtool.models import Requirement
from reqtool.store import Store


def test_every_requirement_in_the_demo_validates_against_the_model(tmp_path):
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "reqtool.cli", "init", "demo", "--repo", str(tmp_path)],
                   check=True, capture_output=True)
    store = Store(tmp_path)
    store.load()
    assert len(store.requirement_map()) > 50
    for uid, data in store.requirement_map().items():
        Requirement.model_validate(data)


def test_a_new_requirement_validates_against_the_model(repo_root):
    store = Store(repo_root)
    store.load()
    Requirement.model_validate(store.create_requirement({"title": "t", "req_type": "story"}))
