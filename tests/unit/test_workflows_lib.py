"""Workflow definitions: normalising, checking and drawing them (no web or files)."""

import pytest

from reqtool import workflows as wf

BASIC = {
    "initial": "draft",
    "states": [
        {"id": "draft", "label": "Draft"},
        {"id": "review", "label": "In Review", "colour": "#d29922"},
        {"id": "done", "label": "Done", "terminal": True},
    ],
    "transitions": {"draft": ["review"], "review": ["done", "draft"]},
    "guards": {"done": {"requires_fields": ["content.rationale"], "requires_ac": True, "message": "Complete it"}},
}


def test_normalise_writes_out_every_setting():
    out = wf.normalise(BASIC)
    assert [s["id"] for s in out["states"]] == ["draft", "review", "done"]
    assert out["states"][0] == {"id": "draft", "label": "Draft", "colour": wf.DEFAULT_COLOUR, "terminal": False}
    assert out["transitions"]["done"] == []                      # every state has a list, even a terminal one
    assert set(out["guards"]) == {"draft", "review", "done"}      # and every state has a full guard
    assert out["guards"]["draft"] == {"requires_fields": [], "requires_ac": False, "requires_children_in": [],
                                      "children_enforce": "warn", "message": ""}
    assert out["guards"]["done"]["requires_fields"] == ["content.rationale"]


def test_normalise_is_idempotent_and_drops_duplicate_targets():
    once = wf.normalise({**BASIC, "transitions": {"draft": ["review", "review"]}})
    assert once["transitions"]["draft"] == ["review"]
    assert wf.normalise(once) == once


def test_a_valid_definition_has_no_errors():
    assert wf.check(BASIC) == ([], [])


@pytest.mark.parametrize("change,fragment", [
    ({"states": []}, "at least one state"),
    ({"initial": "nope"}, "initial state 'nope'"),
    ({"transitions": {"draft": ["ghost"]}}, "unknown state 'ghost'"),
    ({"transitions": {"ghost": ["draft"]}}, "unknown state 'ghost'"),
    ({"guards": {"ghost": {}}}, "unknown state 'ghost'"),
    ({"guards": {"done": {"requires_fields": ["bad path!"]}}}, "not a field path"),
    ({"guards": {"done": {"children_enforce": "sometimes"}}}, "children_enforce"),
    ({"states": [{"id": "Draft"}]}, "lower case"),
    ({"states": [{"id": "a"}, {"id": "a"}]}, "unique"),
    ({"states": [{"id": "a", "colour": "red"}], "initial": "a"}, "hex colour"),
])
def test_errors_are_reported(change, fragment):
    errors, _ = wf.check({**BASIC, **change})
    assert any(fragment in e for e in errors), errors


def test_unreachable_and_dead_end_states_are_warnings_not_errors():
    errors, warnings = wf.check({**BASIC, "states": BASIC["states"] + [{"id": "orphan", "label": "Orphan"}]})
    assert errors == []
    assert any("'orphan' can never be reached" in w for w in warnings)
    assert any("'orphan' can never reach a terminal" in w for w in warnings)


def test_mermaid_draws_states_transitions_and_guards():
    text = wf.to_mermaid(BASIC)
    assert text.startswith("flowchart LR")
    assert 's_draft["Draft"]' in text
    assert 's_done(["Done"])' in text                              # terminal states have a rounded shape
    assert "start_ --> s_draft" in text
    assert "s_draft --> s_review" in text
    assert '|"needs rationale, acceptance criteria"|' in text      # the guard labels the move into the state
    assert "style s_review fill:#d2992233,stroke:#d29922" in text


def test_mermaid_never_contains_a_semicolon_or_unsafe_label_text():
    nasty = {**BASIC, "states": [{"id": "draft", "label": 'Say "hi"; <b>now</b> [x]'}, {"id": "end", "label": "End"}],
             "initial": "draft", "transitions": {"draft": ["end"]},
             "guards": {"end": {"message": "a;b", "requires_fields": ["content.x;y"]}}}
    text = wf.to_mermaid(nasty)
    assert ";" not in text and "<" not in text and "[x]" not in text
    assert "s_end" in text and "\nend" not in text                 # "end" is reserved in Mermaid, so ids are prefixed


def test_mermaid_of_an_empty_workflow_is_still_valid_text():
    assert "No states" in wf.to_mermaid({"states": []})


def test_every_bundled_workflow_checks_clean_and_draws():
    from pathlib import Path
    from reqtool.fileio import load_yaml
    data = load_yaml(Path(wf.__file__).parent / "defaults" / "hierarchy.yaml")
    for wid, definition in data["workflows"].items():
        assert wf.check(definition) == ([], []), wid
        assert ";" not in wf.to_mermaid(definition)
