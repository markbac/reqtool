"""Checking for tools and installing Vale (with a fake download, so no network is used)."""
import hashlib
import io
import tarfile
import zipfile

import pytest
from click.testing import CliRunner

from reqtool import tooling
from reqtool.cli import cli
from reqtool.doclint import vale
from reqtool.doclint.config import ValeSettings

VERSION = "3.9.9"


@pytest.fixture(autouse=True)
def tools_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("REQTOOL_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.delenv("REQTOOL_VALE_VERSION", raising=False)
    return tmp_path / "tools"


def archive(name, body=b"#!/bin/sh\necho vale version 3.9.9\n"):
    if name.endswith(".zip"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("vale.exe", body)
        return buf.getvalue()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for member, data in (("README.md", b"docs"), ("vale", body)):
            info = tarfile.TarInfo(member)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class FakeOpener:
    """Serves a release: the archive and its checksum list. ``tamper`` changes the archive after the sum is made."""

    def __init__(self, name, tamper=False, latest="v3.9.9", missing=()):
        self.name, self.latest, self.missing, self.urls = name, latest, set(missing), []
        self.blob = archive(name)
        self.sums = f"{hashlib.sha256(self.blob).hexdigest()}  {name}\n0000  other_file\n"
        if tamper:
            self.blob += b"x"

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.urls.append(url)
        outer = self

        class Response:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def geturl(self): return f"https://github.com/vale-cli/vale/releases/tag/{outer.latest}"
            def read(self):
                if url.endswith("checksums.txt"):
                    return outer.sums.encode()
                return outer.blob
        if any(m in url for m in self.missing):
            import urllib.error
            raise urllib.error.URLError("offline")
        return Response()


def test_asset_names_follow_the_release_naming():
    assert tooling.asset_name("3.9.1", "Linux", "x86_64") == "vale_3.9.1_Linux_64-bit.tar.gz"
    assert tooling.asset_name("3.9.1", "Darwin", "arm64") == "vale_3.9.1_macOS_arm64.tar.gz"
    assert tooling.asset_name("3.9.1", "Darwin", "x86_64") == "vale_3.9.1_macOS_64-bit.tar.gz"
    assert tooling.asset_name("3.9.1", "Windows", "AMD64") == "vale_3.9.1_Windows_64-bit.zip"
    assert tooling.asset_name("3.9.1", "Linux", "aarch64") == "vale_3.9.1_Linux_arm64.tar.gz"
    with pytest.raises(tooling.ToolError):
        tooling.asset_name("3.9.1", "Plan9", "x86_64")
    with pytest.raises(tooling.ToolError):
        tooling.asset_name("3.9.1", "Linux", "riscv64")


def test_latest_version_comes_from_the_redirect_and_falls_back():
    assert tooling.latest_vale_version(FakeOpener("x", latest="v3.12.0")) == "3.12.0"
    assert tooling.latest_vale_version(FakeOpener("x", latest="weird")) == tooling.FALLBACK_VALE_VERSION
    assert tooling.latest_vale_version(FakeOpener("x", missing=("latest",))) == tooling.FALLBACK_VALE_VERSION


def test_install_downloads_verifies_and_makes_it_runnable(tools_folder):
    opener = FakeOpener(tooling.asset_name(VERSION))
    path = tooling.install_vale(opener=opener)
    assert path == tools_folder / tooling._exe("vale") and path.read_bytes().startswith(b"#!/bin/sh")
    assert path.stat().st_mode & 0o100  # executable
    assert any(u.endswith(f"v{VERSION}/{tooling.asset_name(VERSION)}") for u in opener.urls)
    assert tooling.installed_vale() == path


def test_a_zip_release_is_unpacked_too(tools_folder, monkeypatch):
    monkeypatch.setattr(tooling, "asset_name", lambda v, *a: f"vale_{v}_Windows_64-bit.zip")
    monkeypatch.setattr(tooling, "_exe", lambda n: n + ".exe")
    path = tooling.install_vale(VERSION, FakeOpener(f"vale_{VERSION}_Windows_64-bit.zip"))
    assert path.name == "vale.exe" and path.exists()


def test_a_download_that_does_not_match_its_checksum_is_refused(tools_folder):
    with pytest.raises(tooling.ToolError, match="checksum"):
        tooling.install_vale(opener=FakeOpener(tooling.asset_name(VERSION), tamper=True))
    assert not tools_folder.exists() or not list(tools_folder.iterdir())


def test_a_missing_checksum_entry_is_refused(tools_folder):
    opener = FakeOpener(tooling.asset_name(VERSION))
    opener.sums = "abc  something_else\n"
    with pytest.raises(tooling.ToolError, match="checksum list"):
        tooling.install_vale(opener=opener)


def test_find_vale_prefers_path_then_our_copy(tools_folder, monkeypatch):
    assert tooling.find_vale() is None
    tooling.install_vale(opener=FakeOpener(tooling.asset_name(VERSION)))
    assert tooling.find_vale() == str(tools_folder / tooling._exe("vale"))
    assert tooling.find_vale("some-other-name") is None  # a custom command is never swapped for ours
    monkeypatch.setattr(tooling.shutil, "which", lambda c: "/usr/bin/vale" if c == "vale" else None)
    assert tooling.find_vale() == "/usr/bin/vale"


def test_vale_settings_use_the_installed_copy(tools_folder):
    tooling.install_vale(opener=FakeOpener(tooling.asset_name(VERSION)))
    assert vale.find_binary(ValeSettings()) == str(tools_folder / tooling._exe("vale"))
    assert vale.status(ValeSettings(), None)["available"] is True


def test_ensure_installs_once_then_reports_ok(tools_folder, monkeypatch):
    monkeypatch.setattr(tooling.shutil, "which", lambda c: None if c == "vale" else "/bin/" + c)
    opener = FakeOpener(tooling.asset_name(VERSION))
    first = {s.name: s for s in tooling.ensure_tools(opener=opener)}
    assert first["vale"].ok and "installed in" in first["vale"].detail
    opener.urls.clear()
    again = {s.name: s for s in tooling.ensure_tools(opener=opener)}
    assert again["vale"].ok and opener.urls == []  # nothing downloaded the second time


def test_ensure_check_only_installs_nothing(tools_folder, monkeypatch):
    monkeypatch.setattr(tooling.shutil, "which", lambda c: None if c == "vale" else "/bin/" + c)
    opener = FakeOpener(tooling.asset_name(VERSION))
    statuses = {s.name: s for s in tooling.ensure_tools(install=False, opener=opener)}
    assert not statuses["vale"].ok and opener.urls == []


def test_a_failed_download_is_reported_and_not_retried_for_a_day(tools_folder, monkeypatch):
    monkeypatch.setattr(tooling.shutil, "which", lambda c: None if c == "vale" else "/bin/" + c)
    offline = FakeOpener(tooling.asset_name(VERSION), missing=("checksums",))
    result = {s.name: s for s in tooling.ensure_tools(opener=offline)}
    assert not result["vale"].ok and "not installed" in result["vale"].detail
    assert tooling.recently_failed()
    online = FakeOpener(tooling.asset_name(VERSION))
    skipped = {s.name: s for s in tooling.ensure_tools(opener=online)}
    assert not skipped["vale"].ok and online.urls == [] and "--force" in skipped["vale"].detail
    forced = {s.name: s for s in tooling.ensure_tools(force=True, opener=online)}
    assert forced["vale"].ok and not tooling.recently_failed()


def test_missing_git_is_a_required_failure(monkeypatch):
    monkeypatch.setattr(tooling.shutil, "which", lambda c: None)
    by_name = {s.name: s for s in tooling.check_tools()}
    assert by_name["git"].required and not by_name["git"].ok
    assert not by_name["vale"].required


def test_cli_check_and_exit_codes(monkeypatch):
    monkeypatch.setattr(tooling.shutil, "which", lambda c: None if c in ("vale", "npm") else "/bin/" + c)
    out = CliRunner().invoke(cli, ["tools", "--check"])
    assert out.exit_code == 0, out.output  # optional tools do not fail the run
    assert "absent  vale" in out.output and "ok      git" in out.output
    monkeypatch.setattr(tooling.shutil, "which", lambda c: None)
    assert CliRunner().invoke(cli, ["tools", "--check"]).exit_code == 1  # git is required
