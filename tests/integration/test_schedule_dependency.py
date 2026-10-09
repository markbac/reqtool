"""QA-03 (found by the new lint step): the depends_on schedule check referenced an undefined map and never ran."""
from reqtool.validation import validate_all
from tests.conftest import make_req


def test_dependency_on_later_release_is_warned(client):
    late = make_req(client, title="late", iteration="Sprint-2")
    early = make_req(client, title="early", iteration="Sprint-1",
                     relationships=[{"type": "depends_on", "target": {"uid": late["uid"]}}])
    warns = validate_all(client.app.state.store)["warnings"]
    assert any(w["code"] == "schedule_dependency_conflict" and w["uid"] == early["uid"] for w in warns)


def test_dependency_on_earlier_release_is_fine(client):
    first = make_req(client, title="first", iteration="Sprint-1")
    make_req(client, title="second", iteration="Sprint-2",
             relationships=[{"type": "depends_on", "target": {"uid": first["uid"]}}])
    warns = validate_all(client.app.state.store)["warnings"]
    assert not any(w["code"] == "schedule_dependency_conflict" for w in warns)
