"""PERF-03: a hung Vale binary cannot block the prose check beyond the timeout."""
import os
import stat
import time

from reqtool import validation


def _fake_vale(tmp_path, body):
    exe = tmp_path / "vale"
    exe.write_text("#!/bin/sh\n" + body + "\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


def test_hung_vale_is_abandoned_after_timeout(tmp_path, monkeypatch):
    _fake_vale(tmp_path, "sleep 30")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(validation, "VALE_TIMEOUT_SECONDS", 1)
    start = time.monotonic()
    assert validation.run_vale_lint("The system shall do things.", uid="u", field="content") == []
    assert time.monotonic() - start < 10


def test_normal_vale_output_still_parsed(tmp_path, monkeypatch):
    _fake_vale(tmp_path, """echo '{"f.txt":[{"Severity":"warning","Message":"Too vague","Check":"R.vague","Line":1}]}'""")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    out = validation.run_vale_lint("text", uid="u", field="content")
    assert out and out[0]["code"] == "VALE_PROSE_WARNING" and "Too vague" in out[0]["message"]
