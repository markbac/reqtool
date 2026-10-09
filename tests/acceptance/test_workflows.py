"""QA-07: a release cannot publish unless CI passes, and its smoke tests exist."""
from pathlib import Path

from reqtool.fileio import load_yaml

WF = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _needs(job):
    n = job.get("needs", [])
    return {n} if isinstance(n, str) else set(n)


def test_ci_is_reusable():
    assert "workflow_call" in load_yaml(WF / "ci.yml")["on"]


def test_every_release_job_depends_on_ci_before_publishing():
    jobs = load_yaml(WF / "release.yml")["jobs"]
    assert jobs["ci"]["uses"] == "./.github/workflows/ci.yml"

    def reaches_ci(name, seen=()):
        if name == "ci":
            return True
        return any(reaches_ci(d, seen + (name,)) for d in _needs(jobs[name]) if d not in seen)

    for name in jobs:
        if name != "ci":
            assert reaches_ci(name), f"release job '{name}' can run without CI passing"


def test_release_smoke_tests_are_wired():
    text = (WF / "release.yml").read_text(encoding="utf-8")
    assert text.count("scripts/smoke_release.py") >= 2  # wheel and standalone binary
    assert (WF.parent.parent / "scripts" / "smoke_release.py").exists()
