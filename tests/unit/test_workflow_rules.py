"""The parent/child rule engine: checks up and down, roll-up, cascades, loops, and configuration problems."""

import pytest

from reqtool import workflow_rules as wr
from reqtool.models import HierarchyConfig
from reqtool.stores.hierarchy_store import default_hierarchy_data, parse_hierarchy


def hierarchy(rule_set=None):
    data = default_hierarchy_data()
    data["rules"] = rule_set if rule_set is not None else wr.default_rules("error", "auto")
    return parse_hierarchy(data)


def item(uid, req_type, status, parent=None, **extra):
    return {"uid": uid, "id": uid.upper(), "req_type": req_type, "status": status, "parentId": parent, **extra}


def tree(**statuses):
    """theme > epic > feature > story chain plus a sibling story."""
    return {
        "t": item("t", "theme", statuses.get("t", "draft")),
        "e": item("e", "epic", statuses.get("e", "backlog"), "t"),
        "f": item("f", "feature", statuses.get("f", "backlog"), "e"),
        "s1": item("s1", "story", statuses.get("s1", "backlog"), "f"),
        "s2": item("s2", "story", statuses.get("s2", "backlog"), "f"),
    }


def ok(_item, _to):
    return None


class TestStates:
    def test_tokens_resolve_per_workflow(self):
        h = hierarchy()
        sprint = h.workflows["sprint"]
        assert wr.resolve_states(["@initial"], sprint) == ["backlog"]
        assert wr.resolve_states(["@terminal"], sprint) == ["done", "cancelled"]
        assert wr.resolve_states(["@done"], sprint) == ["done"]
        assert wr.resolve_states(["@cancelled"], sprint) == ["cancelled"]
        assert wr.resolve_states(["@started"], sprint) == ["ready", "in_progress", "in_review"]

    def test_pick_target_takes_the_first_reachable_state(self):
        sprint = hierarchy().workflows["sprint"]
        assert wr.pick_target(sprint, "backlog", ["in_progress", "@started"]) == "in_progress"
        assert wr.pick_target(sprint, "backlog", ["done"]) is None


class TestChecks:
    def test_upward_check_names_the_ancestor_and_distance(self):
        reqs = tree(e="cancelled")
        found = wr.check_move(hierarchy(), reqs, reqs["s1"], "in_progress")
        assert len(found) == 1 and found[0]["rule"] == "no-start-under-closed"
        assert "E, two levels up" in found[0]["message"] and found[0]["mode"] == "error"

    def test_parent_scope_ignores_the_grandparent(self):
        rule_set = wr.default_rules("error", "off")
        rule_set["rules"][0]["scope"] = "parent"
        reqs = tree(e="cancelled")
        assert wr.check_move(hierarchy(rule_set), reqs, reqs["s1"], "in_progress") == []

    def test_levels_limit_how_far_up_it_looks(self):
        rule_set = wr.default_rules("error", "off")
        rule_set["rules"][0]["levels"] = 1
        reqs = tree(e="cancelled")
        assert wr.check_move(hierarchy(rule_set), reqs, reqs["s1"], "in_progress") == []

    def test_downward_check_lists_open_descendants(self):
        reqs = tree(f="in_progress", s1="done")
        found = wr.check_move(hierarchy(), reqs, reqs["f"], "done")
        assert len(found) == 1 and "S2" in found[0]["message"] and "S1" not in found[0]["message"]

    def test_downward_check_reaches_grandchildren_only_when_scoped_to_descendants(self):
        reqs = tree(e="in_progress", f="done", s1="in_progress", s2="done")
        assert wr.check_move(hierarchy(), reqs, reqs["e"], "done")
        rule_set = wr.default_rules("error", "off")
        rule_set["rules"][1]["scope"] = "children"
        assert wr.check_move(hierarchy(rule_set), reqs, reqs["e"], "done") == []

    def test_off_rules_and_unchanged_status_give_nothing(self):
        reqs = tree(f="in_progress")
        assert wr.check_move(hierarchy(wr.default_rules("off", "off")), reqs, reqs["f"], "done") == []
        assert wr.check_move(hierarchy(), reqs, reqs["f"], "in_progress") == []

    def test_a_repository_without_rules_is_unchanged(self):
        reqs = tree(e="cancelled")
        assert wr.check_move(HierarchyConfig(), reqs, reqs["s1"], "in_progress") == []


class TestRollup:
    def test_first_child_to_start_starts_the_whole_chain(self):
        reqs = tree()
        plan = wr.plan_rollups(hierarchy(), reqs, "s1", "backlog", "in_progress", ok)
        # The theme uses the lightweight workflow, so it goes to its own started state.
        assert [(s["uid"], s["to"]) for s in plan["auto"]] == [("f", "in_progress"), ("e", "in_progress"), ("t", "active")]

    def test_last_child_done_completes_the_parent(self):
        reqs = tree(f="in_progress", s1="done", s2="in_progress", e="in_progress", t="active")
        plan = wr.plan_rollups(hierarchy(), reqs, "s2", "in_progress", "done", ok)
        assert [(s["uid"], s["to"]) for s in plan["auto"]][0] == ("f", "done")

    def test_not_all_children_done_does_nothing(self):
        reqs = tree(f="in_progress", s1="done", s2="in_progress")
        plan = wr.plan_rollups(hierarchy(), reqs, "s1", "in_progress", "done", ok)
        assert plan["auto"] == [] and plan["blocked"] == []

    def test_suggest_mode_proposes_and_does_not_chain(self):
        reqs = tree()
        plan = wr.plan_rollups(hierarchy(wr.default_rules("off", "suggest")), reqs, "s1", "backlog", "in_progress", ok)
        assert [s["uid"] for s in plan["suggest"]] == ["f"] and plan["auto"] == []

    def test_a_parent_that_cannot_move_is_reported_not_raised(self):
        reqs = tree()
        plan = wr.plan_rollups(hierarchy(), reqs, "s1", "backlog", "in_progress",
                               lambda it, to: "Field 'owner' is required" if it["uid"] == "f" else None)
        assert plan["auto"] == [] and plan["blocked"][0]["reason"] == "Field 'owner' is required"

    def test_reopening_a_child_reopens_a_done_parent_when_the_workflow_allows_it(self):
        # lightweight allows done -> active, sprint does not.
        reqs = {"t": item("t", "theme", "done"), "i": item("i", "initiative", "done", "t")}
        plan = wr.plan_rollups(hierarchy(), reqs, "i", "done", "active", ok)
        assert [(s["uid"], s["to"]) for s in plan["auto"]] == [("t", "active")]
        sprint = tree(f="done", s1="done")
        blocked = wr.plan_rollups(hierarchy(), sprint, "s1", "done", "in_progress", ok)
        assert blocked["auto"] == [] and "no direct move" in blocked["blocked"][0]["reason"]

    def test_a_new_open_child_reopens_a_done_parent(self):
        reqs = {"t": item("t", "theme", "done"), "i": item("i", "initiative", "draft", "t")}
        plan = wr.plan_rollups(hierarchy(), reqs, "i", None, "draft", ok)
        # A draft child is not started, but it is open: the done parent goes back to active.
        assert [(s["uid"], s["to"]) for s in plan["auto"]] == [("t", "active")]

    def test_cascade_cancel(self):
        rule_set = wr.default_rules("off", "auto")
        rule_set["rules"][-1]["mode"] = "auto"
        reqs = tree(f="in_progress", s1="in_progress", s2="done")
        plan = wr.plan_rollups(hierarchy(rule_set), reqs, "f", "in_progress", "cancelled", ok)
        assert [(s["uid"], s["to"]) for s in plan["auto"]] == [("s1", "cancelled")]

    def test_a_forced_parent_is_left_alone_unless_the_rule_reapplies(self):
        reqs = tree(f="in_progress", s1="done", s2="in_progress")
        reqs["f"]["attributes"] = {"forced": {"status": "in_progress", "rules": ["x"]}}
        plan = wr.plan_rollups(hierarchy(), reqs, "s2", "in_progress", "done", ok)
        assert plan["auto"] == []
        rule_set = wr.default_rules("off", "auto")
        for r in rule_set["rules"]:
            r["reapply"] = True
        again = wr.plan_rollups(hierarchy(rule_set), reqs, "s2", "in_progress", "done", ok)
        assert again["auto"][0]["to"] == "done"

    def test_a_parent_loop_terminates(self):
        reqs = {"a": item("a", "feature", "backlog", "b"), "b": item("b", "feature", "backlog", "a")}
        plan = wr.plan_rollups(hierarchy(), reqs, "a", "backlog", "in_progress", ok)
        assert len(plan["auto"]) <= wr.MAX_DEPTH

    def test_a_very_deep_chain_terminates(self):
        reqs = {"n0": item("n0", "task", "backlog", "n1")}
        for i in range(1, 60):
            reqs[f"n{i}"] = item(f"n{i}", "epic", "backlog", f"n{i + 1}" if i < 59 else None)
        plan = wr.plan_rollups(hierarchy(), reqs, "n0", "backlog", "in_progress", ok)
        assert 0 < len(plan["auto"]) <= wr.MAX_DEPTH


class TestOverrideAndConfig:
    @pytest.mark.parametrize("level,role,allowed", [
        ("editor", "viewer", False), ("editor", "editor", True), ("admin", "editor", False),
        ("admin", "admin", True), ("none", "admin", False)])
    def test_override_follows_the_rule_then_the_default(self, level, role, allowed):
        h = hierarchy()
        assert wr.may_override(h, {"override": level}, role) is allowed

    def test_the_global_default_applies_when_a_rule_has_none(self):
        h = hierarchy()
        assert wr.may_override(h, {"override": None}, "editor") is True
        h.rules.override = "admin"
        assert wr.may_override(h, {"override": None}, "editor") is False

    def test_default_rules_are_valid(self):
        assert wr.check_config(hierarchy()) == []

    def test_config_problems_are_reported(self):
        rule_set = {"override": "boss", "rules": [
            {"id": "a", "kind": "up", "mode": "auto", "scope": "children", "parent_types": ["nope"], "to": ["@bogus"]},
            {"id": "a", "kind": "sideways"},
            {"id": "c", "kind": "complete", "mode": "suggest", "to": ["missing_state"]}]}
        text = "\n".join(wr.check_config(hierarchy(rule_set)))
        for needle in ("override must be", "mode must be one of off, warn, error", "scope must be one of parent",
                       "unknown type 'nope'", "unknown token '@bogus'", "used twice", "kind must be one of",
                       "unknown state 'missing_state'"):
            assert needle in text
