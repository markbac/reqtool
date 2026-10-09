"""What happens when the world changes under the UI: files edited on disk, a server restart, a server that is gone."""

import re

from playwright.sync_api import expect

from .helpers import expand, open_app, seed_tree, select_item, tree_node, wait_until


def requirement_path(server, uid: str):
    return server.root / "requirements" / f"{uid}.yaml"


def test_an_edit_made_on_disk_reaches_the_api_and_the_tree(page):
    ids = seed_tree(page.server)
    open_app(page)
    path = requirement_path(page.server, ids["theme"]["uid"])
    text = path.read_text(encoding="utf-8")
    assert "Theme alpha" in text
    path.write_text(text.replace("Theme alpha", "Theme renamed on disk"), encoding="utf-8")
    wait_until(lambda: page.server.get(f"/requirements/{ids['theme']['uid']}")["title"] == "Theme renamed on disk",
               what="the watcher to pick the edit up")
    page.get_by_title("Refresh tree").click()
    expect(tree_node(page, "TH-001")).to_contain_text("Theme renamed on disk")


def test_a_file_dropped_into_the_repo_appears_as_an_item(page):
    ids = seed_tree(page.server)
    open_app(page)
    source = requirement_path(page.server, ids["story"]["uid"]).read_text(encoding="utf-8")
    clone_uid = "11111111-2222-4333-8444-555555555555"
    text = source.replace(ids["story"]["uid"], clone_uid)
    text = re.sub(r"(?m)^id: .*$", "id: US-900", text)
    text = text.replace("User story one", "Dropped in by hand")
    requirement_path(page.server, clone_uid).write_text(text, encoding="utf-8")
    wait_until(lambda: any(r["title"] == "Dropped in by hand" for r in page.server.get("/requirements")),
               what="the new file to be loaded")


def test_an_idle_server_does_not_keep_reloading(page):
    """Regression for the reload loop: with nothing changing, the revision must stay put."""
    seed_tree(page.server)
    open_app(page)
    before = page.server.get("/health")
    page.wait_for_timeout(3000)
    assert page.server.get("/health") == before
    assert len(page.server.get("/products")) == 1


def test_work_survives_a_server_restart(page):
    ids = seed_tree(page.server)
    open_app(page)
    expand(page, "TH-001")
    page.server.restart()
    page.reload()
    page.locator("select.header-select").first.select_option("p1")
    assert page.server.get(f"/requirements/{ids['story']['uid']}")["title"] == "User story one"
    expect(tree_node(page, "TH-001")).to_be_visible()
    select_item(page, "TH-001")


def test_a_vanished_server_is_reported_and_the_tree_can_be_retried(page):
    seed_tree(page.server)
    open_app(page)
    page.server.stop()
    page.get_by_title("Refresh tree").click()
    expect(page.locator(".sidebar-error")).to_be_visible()
    page.server.restart()
    page.get_by_role("button", name="Retry").click()
    expect(tree_node(page, "TH-001")).to_be_visible()


def test_an_item_deleted_elsewhere_leaves_the_tree_on_refresh(page):
    ids = seed_tree(page.server)
    open_app(page)
    page.server.call("DELETE", f"/requirements/{ids['theme']['uid']}")
    page.get_by_title("Refresh tree").click()
    expect(page.locator(".tree-node", has_text="TH-001")).to_have_count(0)
