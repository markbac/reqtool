"""Use cases run without HTTP: a fake git and a publish recorder stand in for the outside world (ARC-03)."""

import pytest

from reqtool.services.errors import (
    Forbidden, GitFailure, Invalid, MergeConflicts, MissingItem, NotFound, OpenTbd, ServiceError,
    StaleContent, VersionConflict, WorkflowGuard,
)
from reqtool.services.requirements import RequirementService, changed_fields
from reqtool.store import Store
from reqtool.storage import MemoryStorage
from reqtool.vcs import NullVcs


class FakeGit:
    def __init__(self, conflicts=False, fail_commit=False):
        self.conflicts, self.fail_commit = conflicts, fail_commit
        self.staged, self.unstaged, self.commits = [], [], []

    def has_conflicts(self, root):
        return self.conflicts

    def stage_file(self, root, path):
        self.staged.append(path)

    def unstage_file(self, root, path):
        self.unstaged.append(path)

    def commit(self, root, message, name, email, paths=None):
        if self.fail_commit:
            raise RuntimeError("git commit failed: simulated")
        self.commits.append((message, paths))
        return "abc1234"


@pytest.fixture
def events():
    return []


@pytest.fixture
def make(repo_root, events):
    def _make(**git_kwargs):
        store = Store(repo_root)
        store.load()
        git = FakeGit(**git_kwargs)
        return RequirementService(store, lambda event, payload: events.append((event, payload)), git=git), git
    return _make


def test_create_publishes_one_event(make, events):
    service, _ = make()
    created = service.create({"id": "SV-001", "title": "A"})
    assert events == [("requirement_created", {"uid": created["uid"], "id": "SV-001", "req_type": created.get("req_type")})]


def test_every_write_is_refused_while_the_tree_has_merge_conflicts(make):
    service, _ = make()
    created = service.create({"id": "SV-001", "title": "A"})
    service.git.conflicts = True
    for call in (lambda: service.create({"title": "B"}),
                 lambda: service.update(created["uid"], {"title": "x"}),
                 lambda: service.clone(created["uid"]),
                 lambda: service.bulk_update([created["uid"]], {"owner": "x"}, "patch", "s"),
                 lambda: service.approve(created["uid"], "a", None, {"authenticated": False}),
                 lambda: service.commit(created["uid"], "m", None, None)):
        with pytest.raises(MergeConflicts) as info:
            call()
        assert info.value.status == 409


def test_update_detects_a_concurrent_edit_and_unknown_uid(make):
    service, _ = make()
    created = service.create({"id": "SV-001", "title": "A"})
    with pytest.raises(VersionConflict) as info:
        service.update(created["uid"], {"title": "B"}, if_version="9.9.9")
    assert info.value.detail["error"] == "version_conflict"
    assert info.value.detail["your_version"] == "9.9.9"
    with pytest.raises(NotFound):
        service.update("missing", {"title": "B"})


def test_update_publishes_status_changed_only_when_the_status_moves(make, events):
    service, _ = make()
    created = service.create({"id": "SV-001", "title": "A"})
    events.clear()
    service.update(created["uid"], {"title": "B"})
    assert [e for e, _ in events] == ["requirement_updated"]
    events.clear()
    with pytest.raises(WorkflowGuard):
        service.transition(created["uid"], "released")
    assert events == []


def test_transition_needs_a_target(make):
    service, _ = make()
    created = service.create({"id": "SV-001", "title": "A"})
    with pytest.raises(Invalid):
        service.transition(created["uid"], "")


def test_bulk_update_rejects_fields_that_are_not_editable_and_reports_misses(make, events):
    service, _ = make()
    created = service.create({"id": "SV-001", "title": "A"})
    with pytest.raises(Invalid):
        service.bulk_update([created["uid"]], {"uid": "x"}, "patch", "s")
    events.clear()
    out = service.bulk_update([created["uid"], "nope"], {"owner": "sam"}, "patch", "s")
    assert out["updated"] == [created["uid"]] and out["failed"] == ["nope"]
    assert out["errors"] == {"nope": "not found"}
    assert [e for e, _ in events] == ["requirement_updated"]


def test_clone_copies_and_resets(make, events):
    service, _ = make()
    created = service.create({"id": "SV-001", "title": "A"})
    clone = service.clone(created["uid"])
    assert clone["id"] == "SV-001-COPY" and clone["title"] == "A (copy)" and clone["status"] == "draft"
    assert service.clone(created["uid"])["id"] == "SV-001-COPY2"
    with pytest.raises(NotFound):
        service.clone("missing")


def test_approve_uses_the_login_not_the_body(make):
    service, _ = make()
    created = service.create({"id": "SV-001", "title": "A"})
    uid = created["uid"]
    with pytest.raises(Forbidden):
        service.approve(uid, "x", None, {"authenticated": True, "role": "viewer", "username": "v"})
    with pytest.raises(Forbidden):
        service.approve(uid, "x", None, {"authenticated": True, "role": "editor", "username": "e"})
    with pytest.raises(StaleContent) as info:
        service.approve(uid, "a", "sha256:other", {"authenticated": False})
    assert info.value.detail["content_hash"] == created["content_hash"]


def test_approve_is_blocked_by_open_tbds_when_configured(make):
    service, _ = make()
    created = service.create({"id": "SV-001", "title": "A"})
    service.store.config.validation.block_approval_on_open_tbds = True
    service.store.open_tbds_for = lambda req: ["TBD-1"]
    service.store.validate_transition = lambda req, to: None
    with pytest.raises(OpenTbd) as info:
        service.approve(created["uid"], "a", None, {"authenticated": False})
    assert info.value.detail["tbds"] == ["TBD-1"]


def test_commit_stages_and_commits_only_that_file(make):
    service, git = make()
    created = service.create({"id": "SV-001", "title": "A"})
    out = service.commit(created["uid"], " saved ", None, None)
    assert out["commit_sha"] == "abc1234"
    assert git.commits == [("saved", [service.store.req_path(created["uid"])])]


def test_commit_without_a_message_changes_nothing(make):
    service, git = make()
    created = service.create({"id": "SV-001", "title": "A"})
    before = service.store.get_requirement(created["uid"])
    with pytest.raises(Invalid):
        service.commit(created["uid"], "  ", None, None)
    assert service.store.get_requirement(created["uid"]) == before and git.commits == []


def test_a_failed_commit_rolls_the_item_back_and_unstages(make):
    service, git = make(fail_commit=True)
    created = service.create({"id": "SV-001", "title": "A"})
    before = service.store.get_requirement(created["uid"])
    with pytest.raises(GitFailure) as info:
        service.commit(created["uid"], "m", None, None)
    assert info.value.status == 500 and info.value.detail["error"] == "git_error"
    assert service.store.get_requirement(created["uid"]) == before
    assert git.unstaged == [service.store.req_path(created["uid"])]


def test_acceptance_criteria_lifecycle(make, events):
    service, _ = make()
    created = service.create({"id": "SV-001", "title": "A"})
    uid = created["uid"]
    result = service.add_criterion(uid, "It works", None, None)
    ac = result["acceptance_criteria"][-1]
    assert ac["id"].startswith("SV-001__AC-")
    service.update_criterion(uid, ac["uid"], {"text": "It works well"})
    assert service.store.get_requirement(uid)["acceptance_criteria"][-1]["text"] == "It works well"
    with pytest.raises(MissingItem) as info:
        service.update_criterion(uid, "nope", {"text": "x"})
    assert "uid" not in info.value.detail
    service.delete_criterion(uid, ac["uid"])
    assert service.store.get_requirement(uid)["acceptance_criteria"] == []
    assert [e for e, _ in events].count("requirement_updated") == 3


def test_delete_reports_a_missing_item(make, events):
    service, _ = make()
    created = service.create({"id": "SV-001", "title": "A"})
    assert service.delete(created["uid"])["id"] == "SV-001"
    assert events[-1][0] == "requirement_deleted"
    with pytest.raises(NotFound):
        service.delete("missing")


def test_changed_fields_lets_only_clearable_fields_be_nulled():
    assert changed_fields({"owner": None, "title": None, "status": "draft"}) == {"owner": None, "status": "draft"}


def test_service_errors_carry_their_http_shape():
    err = NotFound("u1")
    assert (err.status, err.detail) == (404, {"error": "not_found", "message": "UID 'u1' not found", "uid": "u1"})
    assert isinstance(err, ServiceError)


def test_the_service_runs_against_an_in_memory_store():
    store = Store(__import__("pathlib").Path("/virtual"), storage=MemoryStorage(), vcs=NullVcs())
    store.load()
    seen = []
    service = RequirementService(store, lambda e, p: seen.append(e), git=FakeGit())
    created = service.create({"id": "MEM-001", "title": "In memory"})
    assert service.update(created["uid"], {"title": "Changed"})["title"] == "Changed"
    assert seen == ["requirement_created", "requirement_updated"]
