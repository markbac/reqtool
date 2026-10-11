"""A server started with ``--auth required``: nothing loads until someone logs in, roles are enforced."""

import pytest
from playwright.sync_api import expect

from reqtool.auth import UserStore

from .conftest import start_server
from .helpers import open_menu_item, panel

PASSWORD = "correct-horse-battery"


@pytest.fixture
def server(tmp_path):
    s = start_server(tmp_path / "repo", auth="required")
    users = UserStore(s.root)
    users.create_user("admin", PASSWORD, "Ada Admin", "", "admin")
    users.create_user("vera", PASSWORD, "Vera Viewer", "", "viewer")
    yield s
    s.stop()


def log_in(page, username: str, password: str = PASSWORD) -> None:
    page.goto(page.server.url)
    expect(page.locator("header.header")).to_be_visible()
    p = panel(page, "Server Login")  # the app opens the login panel by itself when the server answers 401
    p.get_by_placeholder("e.g. admin or your username").fill(username)
    p.get_by_placeholder("Enter password").fill(password)
    p.get_by_role("button", name="Login").click()


@pytest.mark.expect_http(401)
def test_a_wrong_password_is_refused_with_a_message(page):
    log_in(page, "admin", "not-the-password")
    expect(page.locator(".side-panel")).to_contain_text("Invalid username or password")
    expect(page.locator(".side-panel")).to_be_visible()


@pytest.mark.expect_http(401)
def test_login_then_the_app_loads_and_logout_returns_to_the_gate(page):
    page.server.headers["Authorization"] = "Bearer " + page.server.post(
        "/auth/login", {"username": "admin", "password": PASSWORD}, expect=200)["access_token"]
    page.server.post("/products", {"id": "p1", "title": "Product One"})
    page.server.headers.clear()

    log_in(page, "admin")
    expect(page.locator("select.header-select").first).to_contain_text("Product One")
    open_menu_item(page, "⚿ Login / Server")
    p = panel(page, "Server Login")
    expect(p).to_contain_text("Active User: Ada Admin")
    expect(p).to_contain_text("admin")
    p.get_by_role("button", name="Logout").click()
    expect(panel(page, "Server Login")).to_be_visible()  # back at the gate
    page.server.get("/products", expect=401)
    expect(page.locator("select.header-select").first).not_to_contain_text("Product One")


@pytest.mark.expect_http(401, 403)
def test_a_viewer_can_read_but_not_write(page):
    token = page.server.post("/auth/login", {"username": "admin", "password": PASSWORD}, expect=200)["access_token"]
    page.server.headers["Authorization"] = f"Bearer {token}"
    page.server.post("/products", {"id": "p1", "title": "Product One"})
    page.server.headers.clear()

    log_in(page, "vera")
    page.locator("select.header-select").first.select_option("p1")
    expect(page.get_by_role("button", name="+ New", exact=True)).to_have_count(0)   # hidden, not offered then refused
    vera = page.server.post("/auth/login", {"username": "vera", "password": PASSWORD}, expect=200)["access_token"]
    page.server.headers["Authorization"] = f"Bearer {vera}"
    assert page.server.post("/requirements", {"title": "x"}, expect=None)["detail"]["error"] == "forbidden"
    page.server.headers["Authorization"] = f"Bearer {token}"
    assert page.server.get("/requirements") == []


@pytest.mark.expect_http(401)
def test_a_viewer_sees_a_read_only_board(page):
    token = page.server.post("/auth/login", {"username": "admin", "password": PASSWORD}, expect=200)["access_token"]
    page.server.headers["Authorization"] = f"Bearer {token}"
    page.server.post("/products", {"id": "p1", "title": "Product One"})
    page.server.post("/requirements", {"title": "A story", "req_type": "story", "content": {"description": "x"}})
    page.server.headers.clear()

    log_in(page, "vera")
    page.locator("select.header-select").first.select_option("p1")
    page.get_by_text("TASK MGMT").click()
    board = page.locator(".kanban-page")
    expect(board.locator(".kanban-card").first).to_be_visible()
    expect(board.locator(".kanban-card[draggable='true']")).to_have_count(0)
    expect(board.get_by_label("Move", exact=False)).to_have_count(0)
    expect(board.get_by_role("button", name="+ New")).to_have_count(0)
