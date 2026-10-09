"""
conftest.py -- Shared pytest fixtures for reqtool tests.
"""
import os
import pytest
import time
from pathlib import Path
from fastapi.testclient import TestClient

# The file watcher leaks inotify descriptors when many apps are built in one process.
os.environ.setdefault("REQTOOL_WATCHER", "0")


@pytest.fixture(autouse=True)
def _fast_password_hashing(monkeypatch):
    """Keep the suite fast; tests of the real work factor set it back explicitly."""
    import reqtool.auth as auth
    monkeypatch.setattr(auth, "PBKDF2_ITERATIONS", 1000)
    monkeypatch.setattr(auth, "login_throttle", auth.LoginThrottle())
    import reqtool.routers.auth as rauth
    monkeypatch.setattr(rauth, "login_throttle", auth.login_throttle)


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """Bare repo directory with required subdirectories."""
    for d in ("requirements", "principles", "decisions", ".reqtool"):
        (tmp_path / d).mkdir()
    return tmp_path


@pytest.fixture
def store(repo_root: Path):
    """Loaded Store instance backed by a fresh temp repo."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from reqtool.store import Store
    s = Store(repo_root)
    s.load()
    return s


@pytest.fixture
def client(repo_root: Path) -> TestClient:
    """FastAPI TestClient backed by a fresh temp repo."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from reqtool.api import create_app
    app = create_app(repo_root)
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def client_with_store(repo_root: Path):
    """Returns (TestClient, Store) sharing the same repo root."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from reqtool.api import create_app
    from reqtool.store import Store
    app = create_app(repo_root)
    tc = TestClient(app)
    s = Store(repo_root)
    s.load()
    return tc, s


# ---------------------------------------------------------------------------
# Helpers used across multiple test modules
# ---------------------------------------------------------------------------

def make_req(client: TestClient, **kwargs) -> dict:
    """POST a minimal requirement and return the response body."""
    payload = {"title": "Test requirement"}
    payload.update(kwargs)
    resp = client.post("/requirements", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def make_principle(client: TestClient, **kwargs) -> dict:
    payload = {"title": "Test principle",
               "content": {"description": "Desc", "rationale": "R",
                           "implications": "", "exceptions": ""}}
    payload.update(kwargs)
    resp = client.post("/principles", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def make_tbd(client: TestClient, **kwargs) -> dict:
    payload = {"title": "Test TBD",
               "content": {"description": "Desc", "impact": "",
                           "resolution_criteria": "", "resolution": None}}
    payload.update(kwargs)
    resp = client.post("/tbds", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def settle(ms: int = 60) -> None:
    """Wait for watchdog to process file events.
    Increase to 150+ ms if tests are flaky in environments with slow I/O.
    """
    time.sleep(ms / 1000)


# ---------------------------------------------------------------------------
# IoT Sensor Demo Repository Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def demo_repo_root(tmp_path: Path) -> Path:
    """Populated IoT Sensor demo repository root directory."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from scripts.create_demo_repo import build_demo_repository
    demo_path = tmp_path / "demo_repo"
    build_demo_repository(demo_path)
    return demo_path


@pytest.fixture
def demo_store(demo_repo_root: Path):
    """Loaded Store instance backed by the IoT Sensor demo repo."""
    from reqtool.store import Store
    s = Store(demo_repo_root)
    s.load()
    return s


@pytest.fixture
def demo_client(demo_repo_root: Path) -> TestClient:
    """FastAPI TestClient backed by the IoT Sensor demo repo."""
    from reqtool.api import create_app
    app = create_app(demo_repo_root)
    return TestClient(app, raise_server_exceptions=True)


def review_first(client, uid, headers=None):
    """Walk a draft requirement through review so it can be approved (the formal workflow has no draft -> approved)."""
    for state in ("in_review", "reviewed"):
        r = client.post(f"/requirements/{uid}/transition", json={"to_state": state}, headers=headers)
        assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Agile fixture repository (QA-01)
# ---------------------------------------------------------------------------
# The IoT demo has no theme, initiative or feature items and almost everything is a draft, so the defects in
# the agile hierarchy could not show up in it. This one has every level and items in several states.

_DESCRIBED = {"description": "Described so that the item validates cleanly."}


def build_agile_repo(client: TestClient) -> dict:
    """Theme > initiative > epic > feature > story > task, plus a bug and a spike, in mixed workflow states.

    Returns each item under a short key. Statuses: the theme is active, one story is done, one is in progress,
    one is in review and the rest are backlog or draft.
    """
    def make(key, req_type, parent=None, **extra):
        fields = {"title": f"{req_type.title()} {key}", "req_type": req_type, "content": _DESCRIBED, **extra}
        if parent:
            fields["parentId"] = items[parent]["uid"]
        items[key] = make_req(client, **fields)

    def move(key, *states):
        for state in states:
            r = client.post(f"/requirements/{items[key]['uid']}/transition", json={"to_state": state})
            assert r.status_code == 200, (key, state, r.text)
            items[key] = r.json()

    items: dict = {}
    make("theme", "theme")
    make("initiative", "initiative", "theme")
    make("epic", "epic", "initiative")
    make("feature", "feature", "epic")
    make("story_done", "story", "feature")
    make("story_doing", "story", "feature")
    make("story_review", "story", "feature")
    make("story_new", "story", "feature")
    make("task", "task", "story_doing")
    make("bug", "bug", "story_doing")
    make("spike", "spike", "epic")
    move("theme", "active")
    move("story_done", "ready", "in_progress", "in_review", "done")
    move("story_doing", "ready", "in_progress")
    move("story_review", "ready", "in_progress", "in_review")
    return items


@pytest.fixture
def agile_client(client: TestClient):
    """``(client, items)``: a TestClient over a repository holding every level of the agile hierarchy."""
    return client, build_agile_repo(client)
