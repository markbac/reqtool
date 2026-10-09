"""The writing checker: text extraction, rules, settings and Vale integration."""
import stat

import pytest

from reqtool.doclint import DocLinter, parse_settings, settings_problems
from reqtool.doclint.config import default_settings, merged_settings
from reqtool.doclint import vale
from reqtool.doclint.text import segments


def linter(**overrides):
    data = merged_settings(overrides)
    return DocLinter(parse_settings(data))


def rules_of(issues):
    return sorted({i.rule for i in issues})


def test_clean_text_has_no_issues():
    assert linter().lint_text("The pump starts within 2 seconds of the button press.") == []


def test_redundant_phrase_gets_suggestion_and_line():
    issues = linter().lint_text("First line.\nWe do it in order to win.")
    assert [(i.rule, i.line, i.suggestion) for i in issues] == [("DOC002", 2, "to")]


def test_glossary_flags_wrong_case_only():
    assert rules_of(linter().lint_text("Use the api over mqtt.")) == ["DOC001"]
    assert linter().lint_text("Use the API over MQTT.") == []


def test_vague_terms():
    issues = linter().lint_text("The UI shall be user-friendly and fast, etc.")
    assert {i.rule for i in issues} == {"REQ001"} and len(issues) == 3


def test_code_urls_and_html_are_not_checked():
    text = "```\nin order to use the api\n```\nSee `api` and https://example.com/api/json and <br> done."
    assert linter().lint_text(text) == []


def test_acronym_must_be_defined_first():
    assert rules_of(linter().lint_text("The RTOS handles it.")) == ["DOC003"]
    assert linter().lint_text("The Real Time Operating System (RTOS) handles it. RTOS is small.") == []
    assert linter().lint_text("RTOS (Real Time Operating System) is small.") == []


def test_shall_rule_is_off_by_default_and_configurable():
    assert linter().lint_text("The pump runs.") == []
    def shall(lint, text):
        return [i for i in lint.lint_item(_item(description=text)) if i.rule == "REQ002"]

    assert shall(linter(), "The pump runs.") == []
    on = linter(disabled_rules=[])
    assert len(shall(on, "The pump runs.")) == 1
    assert shall(on, "The pump shall run.") == []
    assert shall(linter(disabled_rules=[], statement_types=["safety"]), "The pump runs.") == []


def test_severities_follow_settings():
    issues = linter(severities={"DOC002": "error"}).lint_text("in order to")
    assert issues[0].severity == "error"


def test_disabled_rule_is_silent():
    assert linter(disabled_rules=["DOC002", "REQ002"]).lint_text("in order to") == []


def test_custom_glossary_and_phrases():
    cfg = linter(glossary={"Foo": ["foo"]}, redundant_phrases={"utilise": "use"}, vague_terms=[])
    assert rules_of(cfg.lint_text("foo will utilise it")) == ["DOC001", "DOC002"]


def test_segments_report_real_line_numbers():
    parts = [p for p in segments("a\n\n```\ncode\n```\nb\n", "f") if p.text.strip()]
    assert [(p.text.strip(), p.lines[0]) for p in parts] == [("a", 1), ("b", 6)]


def test_settings_validation():
    assert settings_problems(default_settings()) == []
    bad = default_settings()
    bad["severities"]["DOC001"] = "loud"
    bad["fields"] = "content.description"
    bad["vale"]["min_alert_level"] = "nope"
    problems = settings_problems(bad)
    assert len(problems) >= 3
    with pytest.raises(ValueError):
        parse_settings(bad)


def test_merged_settings_fills_every_key():
    merged = merged_settings({"enabled": False, "vale": {"enabled": True}})
    assert merged["enabled"] is False and merged["vale"]["enabled"] is True
    assert merged["vale"]["binary"] == "vale" and set(merged) == set(default_settings())


def _item(**content):
    return {"uid": "u1", "id": "FR-001", "type": "requirement", "req_type": "functional",
            "content": {"description": "", "rationale": "", "extended_description": "", **content},
            "acceptance_criteria": [{"id": "AC-1", "text": "It is fast"}]}


def test_item_lint_covers_configured_fields_and_acceptance_criteria():
    issues = linter().lint_item(_item(description="in order to", rationale="uses the api"))
    found = {(i.field, i.rule) for i in issues}
    assert ("content.description", "DOC002") in found
    assert ("content.rationale", "DOC001") in found
    assert any(f.startswith("acceptance_criteria") and r == "REQ001" for f, r in found)
    assert all(i.uid == "u1" and i.id == "FR-001" for i in issues)


def test_item_lint_respects_fields_setting():
    only = linter(fields=["content.rationale"])
    assert only.lint_item(_item(description="in order to")) == [] or all(
        i.field != "content.description" for i in only.lint_item(_item(description="in order to")))


# -- Vale --------------------------------------------------------------------------------------

def _fake_vale(tmp_path, body):
    script = tmp_path / "fakevale"
    script.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_vale_status_when_missing(tmp_path):
    cfg = parse_settings(merged_settings({"vale": {"enabled": True, "binary": "no-such-vale-binary"}}))
    st = vale.status(cfg.vale, tmp_path)
    assert st["available"] is False


def test_vale_ini_is_generated_from_settings(tmp_path):
    cfg = parse_settings(merged_settings({"vale": {"styles": ["Microsoft"], "disabled_checks": ["Microsoft.Foo"],
                                                    "min_alert_level": "error"}}))
    ini = vale.build_ini(cfg.vale, tmp_path)
    assert "MinAlertLevel = error" in ini and "BasedOnStyles = Microsoft" in ini and "Microsoft.Foo = NO" in ini


def test_vale_results_are_merged(tmp_path):
    out = '{"stdin.md":[{"Line":1,"Check":"INCOSE.Foo","Message":"Bad","Severity":"warning","Match":"x"}]}'
    binary = _fake_vale(tmp_path, f"cat > /dev/null\necho '{out}'\n")
    cfg = parse_settings(merged_settings({"vale": {"enabled": True, "binary": binary}}))
    issues = DocLinter(cfg, tmp_path).lint_text("Hello there.")
    assert any(i.rule.startswith("INCOSE") or "Vale" in i.category or i.message == "Bad" for i in issues)


def test_vale_failure_never_breaks_linting(tmp_path):
    binary = _fake_vale(tmp_path, "exit 3\n")
    cfg = parse_settings(merged_settings({"vale": {"enabled": True, "binary": binary}}))
    assert DocLinter(cfg, tmp_path).lint_text("The pump shall run.") is not None


@pytest.mark.skipif(vale.find_binary(parse_settings(default_settings()).vale) is None, reason="Vale is not installed (run `req tools`)")
def test_real_vale_with_the_bundled_incose_style():
    cfg = parse_settings(merged_settings({"vale": {"enabled": True}}))
    found = DocLinter(cfg).lint_text("The system shall be user-friendly.")
    assert any(i.rule.startswith("vale:INCOSE") for i in found)
