"""The sidebar: the tree's context menu, the child-type menu, the unsaved-changes prompt and the other lists."""

from playwright.sync_api import expect

from .helpers import expand, field, open_app, seed_tree, select_item, tree_node, wait_until


def right_click(page, text: str):
    tree_node(page, text).click(button="right")
    expect(page.locator(".ctx-menu")).to_be_visible()


def ctx(page, label: str):
    page.locator(".ctx-menu .ctx-item", has_text=label).click()


def requirement_ids(server) -> list[str]:
    return sorted(r["id"] for r in server.get("/requirements"))


def test_context_menu_offers_the_five_actions(page):
    seed_tree(page.server)
    open_app(page)
    right_click(page, "TH-001")
    items = page.locator(".ctx-menu .ctx-item")
    assert [i.strip() for i in items.all_inner_texts()] == [
        "+ Add child", "+ Add sibling", "⧉ Clone", "⟳ History", "✕ Delete"]
    page.locator("body").click(position={"x": 5, "y": 5})
    expect(page.locator(".ctx-menu")).to_have_count(0)


def test_add_child_with_one_allowed_type_creates_it_under_the_parent(page):
    ids = seed_tree(page.server)
    allowed = page.server.get("/hierarchy/children/epic")["allowed_children"]
    open_app(page)
    expand(page, "TH-001", "IN-001")
    before = requirement_ids(page.server)
    right_click(page, "EP-001")
    ctx(page, "Add child")
    if len(allowed) > 1:
        page.get_by_role("menuitem").first.click()
    wait_until(lambda: len(requirement_ids(page.server)) == len(before) + 1, what="the new child")
    new = [r for r in page.server.get("/requirements") if r["id"] not in before][0]
    assert page.server.get(f"/requirements/{new['uid']}")["parentId"] == ids["epic"]["uid"]
    expect(page.get_by_role("button", name="Save & Commit")).to_be_visible()


def test_add_child_offers_a_type_menu_when_several_are_allowed(page):
    seed_tree(page.server)
    types = page.server.get("/hierarchy/children/theme")["allowed_children"]
    open_app(page)
    right_click(page, "TH-001")
    ctx(page, "Add child")
    if len(types) > 1:
        menu = page.get_by_role("menu", name="Add child to TH-001")
        expect(menu).to_be_visible()
        assert len(menu.get_by_role("menuitem").all()) == len(types)
        menu.get_by_role("menuitem").first.click()
    wait_until(lambda: len(requirement_ids(page.server)) == 5, what="the new child")


def test_add_sibling_shares_the_parent_and_type(page):
    ids = seed_tree(page.server)
    open_app(page)
    expand(page, "TH-001", "IN-001", "EP-001")
    right_click(page, "US-001")
    ctx(page, "Add sibling")
    wait_until(lambda: len(requirement_ids(page.server)) == 5, what="the sibling")
    new = [r for r in page.server.get("/requirements") if r["uid"] != ids["story"]["uid"]
           and r["req_type"] == "story"][0]
    assert page.server.get(f"/requirements/{new['uid']}")["parentId"] == ids["epic"]["uid"]


def test_clone_creates_a_copy_and_announces_it(page):
    seed_tree(page.server)
    open_app(page)
    expand(page, "TH-001", "IN-001", "EP-001")
    right_click(page, "US-001")
    ctx(page, "Clone")
    expect(page.locator(".toast", has_text="Cloned as")).to_be_visible()
    stories = [r for r in page.server.get("/requirements") if r["req_type"] == "story"]
    assert len(stories) == 2


def test_history_overlay_opens_and_closes(page):
    seed_tree(page.server)
    open_app(page)
    right_click(page, "TH-001")
    ctx(page, "History")
    overlay = page.locator(".history-panel")
    expect(overlay).to_contain_text("History: TH-001")
    overlay.get_by_role("button", name="✕").click()
    expect(overlay).to_have_count(0)


def test_delete_asks_first_and_cancel_keeps_the_item(page):
    ids = seed_tree(page.server)
    open_app(page)
    messages = []
    page.once("dialog", lambda d: (messages.append(d.message), d.dismiss()))
    expand(page, "TH-001", "IN-001", "EP-001")
    right_click(page, "US-001")
    ctx(page, "Delete")
    wait_until(lambda: messages, what="the confirmation")
    assert messages == ["Delete US-001?"]
    assert page.server.get(f"/requirements/{ids['story']['uid']}", expect=200)
    expect(tree_node(page, "US-001")).to_be_visible()


def test_delete_removes_the_item_from_the_tree_and_the_store(page):
    ids = seed_tree(page.server)
    open_app(page)
    page.once("dialog", lambda d: d.accept())
    expand(page, "TH-001", "IN-001", "EP-001")
    right_click(page, "US-001")
    ctx(page, "Delete")
    expect(page.locator(".tree-node", has_text="US-001")).to_have_count(0)
    assert ids["story"]["uid"] not in [r["uid"] for r in page.server.get("/requirements")]


def test_switching_items_with_unsaved_changes_asks_first(page):
    seed_tree(page.server)
    open_app(page)
    select_item(page, "TH-001")
    expand(page, "TH-001")  # selecting a parent toggles it
    field(page, "Title").fill("Edited but not saved")
    seen = []
    page.once("dialog", lambda d: (seen.append(d.message), d.dismiss()))
    tree_node(page, "IN-001").click()
    wait_until(lambda: seen, what="the unsaved-changes prompt")
    assert "unsaved changes" in seen[0]
    assert field(page, "Title").input_value() == "Edited but not saved"
    page.once("dialog", lambda d: d.accept())
    tree_node(page, "IN-001").click()
    expect(field(page, "Title")).to_have_value("Initiative one")


def test_new_button_creates_a_requirement_and_opens_it(page):
    open_app(page)
    page.get_by_role("button", name="+ New", exact=True).first.click()
    wait_until(lambda: page.server.get("/requirements"), what="the new requirement")
    expect(field(page, "Title")).to_have_value("New requirement")


def test_expand_all_toggle_opens_every_level(page):
    seed_tree(page.server)
    open_app(page)
    page.get_by_title("Expand all").click()
    expect(page.locator(".tree-node", has_text="US-001")).to_be_visible()
    page.get_by_title("Collapse all").click()


def test_principles_list_creates_and_filters(page):
    open_app(page)
    page.locator(".sidebar-tab", has_text="Principles").click()
    page.get_by_role("button", name="+ New", exact=True).click()
    wait_until(lambda: page.server.get("/principles"), what="the new principle")
    expect(field(page, "Title")).to_have_value("New principle")
    search = page.get_by_placeholder("Search principles...")
    search.fill("zzz-nothing")
    expect(page.locator(".list-item")).to_have_count(0)
    search.fill("")
    expect(page.locator(".list-item")).to_have_count(1)


def test_tbd_list_creates_and_resolves(page):
    open_app(page)
    page.locator(".sidebar-tab", has_text="TBDs").click()
    page.get_by_role("button", name="+ New", exact=True).click()
    wait_until(lambda: page.server.get("/tbds"), what="the new TBD")
    expect(page.locator(".list-item", has_text="New TBD")).to_be_visible()
    page.locator(".list-item").get_by_role("button", name="✓ Resolve").click()
    expect(page.locator(".modal, [role=dialog]").first).to_be_visible()
