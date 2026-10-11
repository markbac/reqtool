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
    for hidden in ("⌂ Repository", "⇌ Webhooks", "⊙ Vocabularies"):
        expect(page.get_by_role("menuitem", name=hidden)).to_have_count(0)
    page.get_by_role("menuitem", name="⬡ Workflows").click()
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
    for name in ("+ Product", "⊕ Module"):
        expect(page.get_by_role("button", name=name, exact=True)).to_have_count(admin_buttons)
    expect(page.get_by_role("button", name="+ New", exact=True)).to_have_count(new_button)


@pytest.mark.expect_http(401)
def test_an_administrator_has_everything(page):
    log_in(page, "root")
    page.locator("select.header-select").first.select_option("p1")
    select_item(page, page.server.item["id"])
    expect(page.get_by_role("button", name="Delete", exact=True)).to_be_visible()
    page.get_by_role("button", name="⋯ More").click()
    for shown in ("⌂ Repository", "⇌ Webhooks", "⬡ Workflows", "✎ Writing check"):
        expect(page.get_by_role("menuitem", name=shown)).to_be_visible()


@pytest.mark.expect_http(401)
@pytest.mark.parametrize("user, headings, hidden", [
    ("root", ["View", "Create and import", "Quality", "Configure", "Admin", "Account"], []),
    ("ed", ["View", "Create and import", "Quality", "Configure", "Admin", "Account"], ["⇌ Webhooks", "⌂ Repository", "⊙ Vocabularies"]),
    ("vw", ["View", "Create and import", "Quality", "Configure", "Admin", "Account"], ["≡ Bulk update", "⇪ Import CSV", "⇌ Webhooks", "⌂ Repository"]),
])
def test_the_more_menu_is_grouped_and_follows_the_role(page, user, headings, hidden):
    log_in(page, user)
    page.get_by_role("button", name="⋯ More").click()
    menu = page.get_by_role("menu", name="More tools")
    for heading in headings:
        expect(menu.get_by_role("group", name=heading)).to_be_visible()
    for label in hidden:
        expect(menu.get_by_role("menuitem", name=label)).to_have_count(0)


@pytest.mark.expect_http(401)
def test_a_group_with_nothing_for_the_role_is_dropped(page):
    log_in(page, "vw")
    page.get_by_role("button", name="⋯ More").click()
    menu = page.get_by_role("menu", name="More tools")
    expect(menu.get_by_role("group", name="Create and import")).to_be_visible()   # iterations, diagram: open to read
    menu.get_by_label("Find a tool").fill("webhook")
    expect(menu.get_by_role("group")).to_have_count(0)
    expect(menu).to_contain_text("Nothing matches")


@pytest.mark.expect_http(401)
def test_the_more_menu_is_searchable_and_works_from_the_keyboard(page):
    log_in(page, "root")
    page.get_by_role("button", name="⋯ More").click()
    menu = page.get_by_role("menu", name="More tools")
    expect(menu.get_by_label("Find a tool")).to_be_focused()
    menu.get_by_label("Find a tool").fill("roadm")
    expect(menu.get_by_role("menuitem")).to_have_count(1)
    page.keyboard.press("Escape")
    expect(menu).to_have_count(0)
    page.get_by_role("button", name="⋯ More").click()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    expect(page.get_by_role("menu", name="More tools")).to_have_count(0)
    panel(page, "Overview")
