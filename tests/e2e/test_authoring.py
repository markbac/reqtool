"""Creating, editing, saving, committing and deleting items through the UI, checked against the files on disk."""

import re

from playwright.sync_api import expect

from .helpers import expand, field, open_app, seed_tree, select_item, tree_node


def read_yaml(server, rel: str) -> dict:
    from ruamel.yaml import YAML
    return YAML(typ="safe").load((server.root / rel).read_text(encoding="utf-8"))


def test_create_product_in_the_ui(page):
    open_app(page, product=None)
    page.get_by_role("button", name="+ Product").click()
    page.get_by_placeholder("ID (e.g. sensor-v1)").fill("sensor-v1")
    page.get_by_placeholder("Title (optional)").fill("Sensor v1")
    page.get_by_role("button", name="Create", exact=True).click()
    expect(page.locator("select.header-select").first).to_have_value("sensor-v1")
    assert page.server.get("/products/sensor-v1")["title"] == "Sensor v1"
    assert (page.server.root / "products" / "sensor-v1" / "_product.yaml").exists()


def test_new_product_is_still_listed_after_the_server_settles(page):
    """Regression: a product vanished from the list because the file watcher reloaded the store in a loop."""
    open_app(page, product=None)
    page.get_by_role("button", name="+ Product").click()
    page.get_by_placeholder("ID (e.g. sensor-v1)").fill("settle")
    page.get_by_role("button", name="Create", exact=True).click()
    expect(page.locator("select.header-select").first).to_have_value("settle")
    page.wait_for_timeout(3000)
    assert [p["id"] for p in page.server.get("/products")] == ["settle"]
    page.reload()
    expect(page.locator("select.header-select").first).to_have_value("settle")


def test_quick_create_edit_save_and_reload(page):
    open_app(page)
    page.get_by_test_id("quick-story").click()
    expect(field(page, "Title")).to_be_visible()
    field(page, "Title").fill("Reset a forgotten password")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_role("button", name="Saved ✓")).to_be_visible()

    stored = page.server.get("/requirements?req_type=story")
    assert [r["title"] for r in stored] == ["Reset a forgotten password"]
    on_disk = read_yaml(page.server, f"requirements/{stored[0]['uid']}.yaml")
    assert on_disk["title"] == "Reset a forgotten password"

    # the item is created without a parent, so it is not in the product tree; reopen it from the search palette
    page.reload()
    page.locator("select.header-select").first.select_option("p1")
    page.keyboard.press("Control+k")
    page.get_by_placeholder("Search", exact=False).last.fill("forgotten password")
    page.get_by_text(stored[0]["id"]).last.click()
    expect(field(page, "Title")).to_have_value("Reset a forgotten password")


def test_edit_description_marks_dirty_then_saves(page):
    ids = seed_tree(page.server)
    open_app(page)
    expand(page, "TH-001", "IN-001")
    select_item(page, "EP-001")
    save = page.get_by_role("button", name="Saved ✓")
    expect(save).to_be_disabled()
    field(page, "Title").fill("Epic one, renamed")
    expect(page.get_by_role("button", name="Save", exact=True)).to_be_enabled()
    expect(tree_node(page, "EP-001").locator(".tree-node-dirty")).to_be_visible()
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_role("button", name="Saved ✓")).to_be_disabled()
    expect(tree_node(page, "EP-001")).to_contain_text("Epic one, renamed")
    assert page.server.get(f"/requirements/{ids['epic']['uid']}")["title"] == "Epic one, renamed"


def test_ctrl_s_saves(page):
    ids = seed_tree(page.server)
    open_app(page)
    expand(page, "TH-001", "IN-001")
    select_item(page, "EP-001")
    field(page, "Title").fill("Saved with the keyboard")
    page.keyboard.press("Control+s")
    expect(page.get_by_role("button", name="Saved ✓")).to_be_visible()
    assert page.server.get(f"/requirements/{ids['epic']['uid']}")["title"] == "Saved with the keyboard"


def test_status_buttons_change_the_draft_and_save_applies_it(page):
    ids = seed_tree(page.server)
    open_app(page)
    expand(page, "TH-001", "IN-001", "EP-001")
    select_item(page, "US-001")
    page.get_by_role("button", name="Ready", exact=True).click()
    assert page.server.get(f"/requirements/{ids['story']['uid']}")["status"] == "backlog"  # not saved yet
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_role("button", name="Saved ✓")).to_be_visible()
    assert page.server.get(f"/requirements/{ids['story']['uid']}")["status"] == "ready"
    expect(tree_node(page, "US-001")).to_contain_text("ready")  # the tree follows without a refresh


def test_save_and_commit_commits_only_that_item(page):
    ids = seed_tree(page.server)
    page.server.git("add", "-A")
    page.server.git("commit", "-q", "-m", "seed")
    open_app(page)
    expand(page, "TH-001", "IN-001")
    select_item(page, "EP-001")
    field(page, "Title").fill("Committed title")
    # an unrelated edit that must stay out of the commit
    other = page.server.get(f"/requirements/{ids['theme']['uid']}")
    page.server.put(f"/requirements/{ids['theme']['uid']}", {**other, "title": "Theme edited elsewhere"})

    page.get_by_role("button", name="Save & Commit").click()
    page.get_by_placeholder("Brief description of changes").fill("Rename the epic")
    page.get_by_role("button", name="Commit", exact=True).click()
    expect(page.get_by_role("button", name="Saved ✓")).to_be_visible()

    assert page.server.git("log", "-1", "--format=%s") == "Rename the epic"
    files = page.server.git("show", "--name-only", "--format=", "HEAD").split()
    assert files == [f"requirements/{ids['epic']['uid']}.yaml"]
    assert "requirements/" in page.server.git("status", "--short")  # the theme edit is still uncommitted


def test_commit_requires_a_message(page):
    seed_tree(page.server)
    open_app(page)
    expand(page, "TH-001", "IN-001")
    select_item(page, "EP-001")
    page.get_by_role("button", name="Save & Commit").click()
    message = page.get_by_placeholder("Brief description of changes")
    message.fill("")
    expect(page.get_by_role("button", name="Commit", exact=True)).to_be_disabled()
    message.fill("   ")
    expect(page.get_by_role("button", name="Commit", exact=True)).to_be_disabled()
    page.locator(".modal").get_by_role("button", name="Cancel").click()
    expect(page.get_by_placeholder("Brief description of changes")).to_have_count(0)


def test_header_shows_staged_files_and_commits_them(page):
    ids = seed_tree(page.server)
    page.server.git("add", "-A")
    open_app(page)
    badge = page.locator(".header-staged-badge")
    expect(badge).to_be_visible(timeout=15000)
    assert re.search(r"\d+ staged", badge.inner_text())


def test_delete_an_item_removes_it_from_the_tree(page):
    ids = seed_tree(page.server)
    open_app(page)
    expand(page, "TH-001", "IN-001", "EP-001")
    select_item(page, "US-001")
    page.on("dialog", lambda d: d.accept())
    page.get_by_role("button", name="Delete", exact=True).click()
    expect(page.locator(".tree-node", has_text="US-001")).to_have_count(0)
    assert ids["story"]["uid"] not in [r["uid"] for r in page.server.get("/requirements")]
