"""CI helper: failed tests become GitHub annotations."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("ci_failures", Path(__file__).parent.parent / "scripts" / "ci_failures.py")
ci_failures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci_failures)

XML = """<testsuites><testsuite>
<testcase classname="tests.test_a" name="test_ok"/>
<testcase classname="tests.test_a" name="test_bad"><failure message="assert 1 == 2&#10;detail">trace</failure></testcase>
<testcase classname="tests.test_b" name="test_err"><error message="boom"/></testcase>
</testsuite></testsuites>"""


def test_reports_failures_and_errors_only(tmp_path, capsys, monkeypatch):
    f = tmp_path / "j.xml"
    f.write_text(XML)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    ci_failures.main([str(f)])
    out = capsys.readouterr().out
    assert "::error title=Test failed: tests.test_a::test_bad::assert 1 == 2%0Adetail" in out
    assert "tests.test_b::test_err" in out and "test_ok" not in out
    assert "tests.test_a::test_bad" in summary.read_text()


def test_unreadable_file_is_reported_not_raised(tmp_path, capsys):
    ci_failures.main([str(tmp_path / "missing.xml")])
    assert "could not read JUnit file" in capsys.readouterr().out
