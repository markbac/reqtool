"""
conftest.py -- Shared pytest fixtures for reqtool tests.
"""
import pytest
import time
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """Bare repo directory with required subdirectories."""
    for d in ("requirements", "principles", "tbds", ".reqtool"):
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
