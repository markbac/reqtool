"""Browser tests (QA-02): drive the real UI against a real ``req serve`` process.

These need Playwright and a Chromium build (``pip install -e ".[e2e]"`` then ``playwright install chromium``)
and the built UI (``npm run build`` in ``src/reqtool/ui``). Without them the whole directory is skipped, so the
ordinary unit-test jobs are unaffected. Set ``REQTOOL_E2E_REQUIRED=1`` (CI does) to make a missing piece an
error instead of a skip.

Every page runs offline: requests to anything but the test server are refused, and a console error, an
uncaught exception or an HTTP 4xx/5xx the test did not expect fails the test.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
UI_INDEX = ROOT / "src" / "reqtool" / "ui" / "dist" / "index.html"
REQUIRED = os.environ.get("REQTOOL_E2E_REQUIRED") == "1"


collect_ignore_glob: list[str] = []  # pytest skips a directory by ignoring its test files (a conftest cannot skip)


def _unavailable(reason: str) -> None:
    if REQUIRED:
        pytest.fail(f"browser tests are required but {reason}", pytrace=False)
    collect_ignore_glob.append("test_*.py")


try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None
    _unavailable("playwright is not installed")
if not UI_INDEX.exists():
    _unavailable("the UI is not built (run `npm run build` in src/reqtool/ui)")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    """A running ``req serve`` on a throw-away git repository, with a small JSON client."""

    def __init__(self, root: Path, port: int, proc: subprocess.Popen):
        self.root, self.port, self.proc = root, port, proc
        self.url = f"http://127.0.0.1:{port}"
        self.headers: dict[str, str] = {}  # for example a bearer token when the server requires a login

    def call(self, method: str, path: str, body=None, expect: int | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", **self.headers})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        if expect is not None:
            assert status == expect, f"{method} {path} -> {status}: {raw[:300]!r}"
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            return raw

    def get(self, path, **kw):
        return self.call("GET", path, **kw)

    def post(self, path, body=None, expect: int | None = 201):
        return self.call("POST", path, body if body is not None else {}, expect=expect)

    def put(self, path, body, expect: int | None = 200):
        return self.call("PUT", path, body, expect=expect)

    def req(self, **fields) -> dict:
        """Create a requirement through the API."""
        fields.setdefault("title", "Seeded requirement")
        return self.post("/requirements", fields)

    def git(self, *args: str) -> str:
        return _git(self.root, *args)

    def restart(self) -> None:
        """Stop the process and start a new one on the same repository and port (state must survive)."""
        self.stop()
        fresh = _launch(self.root, self.port, getattr(self, "auth", None))
        self.proc = fresh.proc

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def _env() -> dict:
    # Run the checkout under test, not whichever copy of reqtool happens to be installed.
    src = str(ROOT / "src")
    # tests/conftest.py turns the file watcher off for unit tests; the real server runs with it on.
    return {**os.environ, "PYTHONWARNINGS": "ignore", "REQTOOL_WATCHER": "1",
            "PYTHONPATH": os.pathsep.join(filter(None, [src, os.environ.get("PYTHONPATH")]))}


def _launch(root: Path, port: int, auth: str | None) -> Server:
    cmd = [sys.executable, "-m", "reqtool.cli", "serve", "--repo", str(root), "--port", str(port)]
    if auth:
        cmd += ["--auth", auth]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=_env(), text=True)
    server = Server(root, port, proc)
    server.auth = auth
    deadline = time.time() + 40
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"req serve exited early:\n{proc.stdout.read() if proc.stdout else ''}")
        try:
            urllib.request.urlopen(server.url + "/health", timeout=1).read()
            return server
        except urllib.error.HTTPError:
            return server  # answering, even if it wants a login
        except OSError:
            time.sleep(0.2)
    server.stop()
    raise RuntimeError("req serve did not start")


def start_server(root: Path, flavour: str = "agile", auth: str | None = None) -> Server:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "e2e@example.com")
    _git(root, "config", "user.name", "E2E")
    subprocess.run([sys.executable, "-m", "reqtool.cli", "init", flavour, "--repo", str(root),
                    "--id", "e2e", "--title", "E2E"], check=True, capture_output=True, env=_env())
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return _launch(root, _free_port(), auth)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        exe = os.environ.get("REQTOOL_E2E_CHROMIUM")
        try:
            args = ["--disable-background-networking", "--disable-sync"]  # nothing leaves the machine
            b = p.chromium.launch(executable_path=exe, args=args) if exe else p.chromium.launch(args=args)
        except Exception as exc:  # no browser installed
            if REQUIRED:
                pytest.fail(f"browser tests are required but Chromium is not available ({str(exc).splitlines()[0]})")
            pytest.skip(f"Chromium is not available ({str(exc).splitlines()[0]})")
        yield b
        b.close()


@pytest.fixture
def server(tmp_path, request):
    """A fresh repository and server for one test (independent of every other test).

    ``@pytest.mark.parametrize("server", ["defaults"], indirect=True)`` picks another ``req init`` flavour.
    """
    s = start_server(tmp_path / "repo", getattr(request, "param", "agile"))
    yield s
    s.stop()


@pytest.fixture
def page(browser, server, request):
    """A page on ``server`` that fails the test on console errors, page errors and unexpected HTTP errors.

    A test that deliberately triggers an error lists the statuses it expects with
    ``@pytest.mark.expect_http(409, 422)``.
    """
    ctx = browser.new_context(viewport={"width": 1500, "height": 950}, accept_downloads=True)
    ctx.route("**/*", lambda route: route.continue_() if route.request.url.startswith(server.url) else route.abort())
    pg = ctx.new_page()
    problems: list[str] = []
    marker = request.node.get_closest_marker("expect_http")
    allowed = set(marker.args) if marker else set()

    pg.on("console", lambda m: problems.append(f"console.error: {m.text}")
          if m.type == "error" and "Failed to load resource" not in m.text else None)
    pg.on("pageerror", lambda e: problems.append(f"uncaught: {e}"))
    pg.on("response", lambda r: problems.append(f"HTTP {r.status} {r.request.method} {r.url}")
          if r.status >= 400 and r.status not in allowed and r.url.startswith(server.url) else None)
    pg.set_default_timeout(15_000)
    pg.server = server  # type: ignore[attr-defined]
    from . import helpers
    helpers.CURRENT_PAGE[:] = [pg]
    yield pg
    helpers.CURRENT_PAGE.clear()
    report = getattr(request.node, "rep_call", None)
    if report is not None and report.failed:  # a picture of what the user would have seen (CI uploads this folder)
        out = ROOT / "test-results"
        out.mkdir(exist_ok=True)
        try:
            pg.screenshot(path=str(out / f"{request.node.name}.png"), full_page=True)
        except Exception:
            pass
    ctx.close()
    assert not problems, "browser reported problems:\n" + "\n".join(problems)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    setattr(item, "rep_" + call.when, outcome.get_result())


def pytest_configure(config):
    config.addinivalue_line("markers", "expect_http(*statuses): HTTP error statuses this test provokes on purpose")
