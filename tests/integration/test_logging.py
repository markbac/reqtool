"""Logging is configured with ctxlogkit: lines go to stderr and carry the logged-in user."""
import logging

from click.testing import CliRunner
from ctxlogkit import get_log_context
from fastapi.testclient import TestClient

from reqtool.api import create_app
from reqtool.auth import UserStore
from reqtool.cli import cli
from reqtool.logconfig import configure_logging

PW = "correct-horse-battery"


def test_request_log_context_carries_user(repo_root):
    UserStore(repo_root).create_user("ed", PW, role="editor")
    app = create_app(repo_root, auth_mode="required")

    @app.get("/_log_probe")
    def _probe():
        return {"user_id": get_log_context()["user_id"]}

    c = TestClient(app)
    token = c.post("/auth/login", json={"username": "ed", "password": PW}).json()["access_token"]
    r = c.get("/_log_probe", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"user_id": "ed"}


def test_logs_go_to_stderr_not_stdout(capsys, monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    configure_logging()  # what every `req` command does first
    logging.getLogger("reqtool.probe").warning("probe-warning")
    logging.getLogger("reqtool.probe").info("probe-info")
    out, err = capsys.readouterr()
    assert "probe-warning" in err
    assert "probe-info" not in err  # the CLI default is WARNING
    assert out == ""


def test_cli_configures_logging(repo_root):
    for h in list(logging.getLogger("reqtool").handlers):
        logging.getLogger("reqtool").removeHandler(h)
    result = CliRunner().invoke(cli, ["validate", "--repo", str(repo_root)])
    assert result.exception is None or isinstance(result.exception, SystemExit), result.output
    assert logging.getLogger("reqtool").handlers
