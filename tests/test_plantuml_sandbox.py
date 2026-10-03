"""SEC-10: PlantUML runs sandboxed, with bounded input and no file/URL includes."""
import subprocess
import pytest

import reqtool.routers.system as system


@pytest.mark.parametrize("src", [
    "!include /etc/passwd\nA -> B",
    "A -> B\n  !includeurl http://169.254.169.254/\n",
    "!INCLUDESUB file.puml!X\nA->B",
    "!import lib.zip\nA->B",
    "!theme plain from https://example.com/themes\nA->B",
])
def test_file_and_url_directives_are_refused(client, src):
    r = client.post("/render/plantuml", json={"text": src})
    assert r.status_code == 422
    assert "not allowed" in r.json()["detail"]["message"]


def test_oversized_source_is_413(client):
    r = client.post("/render/plantuml", json={"text": "A -> B\n" * 30_000})
    assert r.status_code == 413


def test_plain_diagram_is_not_blocked(client):
    r = client.post("/render/plantuml", json={"text": "Alice -> Bob : hi"})
    assert r.status_code == 200  # fallback svg or real render


def test_subprocess_gets_sandbox_profile_and_errors_keep_status(client, tmp_path, monkeypatch):
    jar = tmp_path / "plantuml.jar"
    jar.write_bytes(b"x")
    monkeypatch.setenv("PLANTUML_JAR", str(jar))
    monkeypatch.setattr(system.shutil, "which", lambda name: "/usr/bin/java")
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 1, b"", b"Syntax Error")

    monkeypatch.setattr(system.subprocess, "run", fake_run)
    r = client.post("/render/plantuml", json={"text": "A -> B"})
    assert seen["env"]["PLANTUML_SECURITY_PROFILE"] == "SANDBOX"
    assert seen["timeout"] == 15
    assert r.status_code == 400  # render errors stay 400, not rewrapped as 500
