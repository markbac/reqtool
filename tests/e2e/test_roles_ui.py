"""What each role sees: editors cannot delete or administer, viewers cannot change anything (auth required)."""

import pytest
from playwright.sync_api import expect

from reqtool.auth import UserStore

from .conftest import start_server
from .helpers import field, panel, select_item

PASSWORD = "correct-horse-battery"


@pytest.fixture
def secured(tmp_path):
    s = start_server(tmp_path / "repo", "defaults", auth="required")
    users = UserStore(s.root)
    users.create_user("root", PASSWORD, "Ada Admin", "", "admin")
    users.create_user("ed", PASSWORD, "Eddie Editor", "", "editor")
    users.create_user("vw", PASSWORD, "Vera Viewer", "", "viewer")
    token = s.post("/auth/login", {"username": "root", "password": PASSWORD}, expect=200)["access_token"]
    s.headers["Authorization"] = f"Bearer {token}"
    s.post("/products", {"id": "p1", "title": "Product One"})
    s.item = s.req(title="Pump", req_type="functional", content={"description": "The pump shall run."})
    s.put("/products/p1", {"root_requirements": [{"uid": s.item["uid"]}]}, expect=None)
    s.headers.clear()
    yield s
    s.stop()


@pytest.fixture
def server(secured):
    return secured


def log_in(page, username):
    page.goto(page.server.url)
    expect(page.locator("header.header")).to_be_visible()
    p = panel(page, "Server Login")
    p.get_by_placeholder("e.g. admin or your username").fill(username)
    p.get_by_placeholder("Enter password").fill(PASSWORD)
    p.get_by_role("button", name="Login").click()
    expect(page.locator("select.header-select").first).to_contain_text("Product One")




@pytest.mark.expect_http(401)
def test_an_editor_edits_but_cannot_delete_or_administer(page):
    log_in(page, "ed")
    page.locator("select.header-select").first.select_option("p1")
    select_item(page, page.server.item["id"])
    expect(page.get_by_role("button", name="Save & Commit")).to_be_enabled()
    expect(page.get_by_role("button", name="Delete", exact=True)).to_have_count(0)
    page.get_by_role("button", name="⋯ More").click()
    for hidden in ("📦 Repository", "⇌ Webhooks", "⊙ Vocabularies", "⬡ Fallback workflow"):
        expect(page.get_by_role("button", name=hidden)).to_have_count(0)
    page.get_by_role("button", name="⬡ Workflows").click()
    p = panel(page, "Workflows")
    expect(p).to_contain_text("only an administrator can change them")
    expect(p.get_by_role("button", name="Save", exact=True)).to_have_count(0)
    expect(p.get_by_label("New state id")).to_have_count(0)


@pytest.mark.expect_http(401)
def test_a_viewer_sees_a_read_only_item(page):
    log_in(page, "vw")
    page.locator("select.header-select").first.select_option("p1")
    select_item(page, page.server.item["id"])
    expect(page.get_by_text("Read-only: your role can view this item")).to_be_visible()
    expect(page.get_by_role("button", name="Save & Commit")).to_be_disabled()
    expect(page.get_by_role("button", name="Delete", exact=True)).to_have_count(0)
    expect(field(page, "Title")).to_be_disabled()
    expect(page.locator(".wf-transition-btn")).to_have_count(0)


@pytest.mark.expect_http(401)
@pytest.mark.parametrize("user, admin_buttons, new_button", [("root", 1, 1), ("ed", 0, 1), ("vw", 0, 0)])
def test_create_and_admin_buttons_follow_the_role(page, user, admin_buttons, new_button):
    """UI-25: controls a role cannot use are not shown (editor: no Product, Repo or Module; viewer: no New either)."""
    log_in(page, user)
    page.locator("select.header-select").first.select_option("p1")
    for name in ("+ Product", "📦 Repo", "⊕ Module"):
        expect(page.get_by_role("button", name=name, exact=True)).to_have_count(admin_buttons)
    expect(page.get_by_role("button", name="+ New", exact=True)).to_have_count(new_button)


@pytest.mark.expect_http(401)
def test_an_administrator_has_everything(page):
    log_in(page, "root")
    page.locator("select.header-select").first.select_option("p1")
    select_item(page, page.server.item["id"])
    expect(page.get_by_role("button", name="Delete", exact=True)).to_be_visible()
    page.get_by_role("button", name="⋯ More").click()
    for shown in ("📦 Repository", "⇌ Webhooks", "⬡ Fallback workflow", "⬡ Workflows", "✎ Writing check"):
        expect(page.get_by_role("button", name=shown)).to_be_visible()
