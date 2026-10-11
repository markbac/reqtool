"""The empty editor's create buttons (UI-20, UI-21): they create, open and show the item."""

from playwright.sync_api import expect

from .helpers import open_app, wait_until


def test_quick_create_makes_the_item_and_shows_it_in_the_tree(page):
    open_app(page)
    page.get_by_test_id("quick-epic").click()
    items = wait_until(lambda: page.server.get("/requirements"), what="the quick-created epic")
    assert [i["req_type"] for i in items] == ["epic"]
    expect(page.locator(".tree-node", has_text="New Epic").first).to_be_visible()
    expect(page.get_by_role("button", name="Save & Commit")).to_be_visible()


def test_quick_create_offers_the_repositorys_types(page):
    open_app(page)
    types = page.server.get("/hierarchy/types")
    for type_id in types:
        expect(page.get_by_test_id(f"quick-{type_id}")).to_be_visible()


def test_a_template_card_creates_the_item_and_shows_it(page):
    templates = page.server.get("/templates")
    assert templates, "the agile flavour ships templates"
    open_app(page)
    card = page.get_by_test_id(f"template-{templates[0]['id']}")
    card.click()
    items = wait_until(lambda: page.server.get("/requirements"), what="the item made from the template")
    assert len(items) == 1
    expect(page.locator(".tree-node").first).to_be_visible()
    expect(page.get_by_role("button", name="Save & Commit")).to_be_visible()
