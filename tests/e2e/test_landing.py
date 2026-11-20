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


WORK = {"theme", "initiative", "epic", "feature", "story", "task", "bug", "spike", "issue"}


def test_quick_create_offers_the_repositorys_types_in_their_own_area(page):
    types = page.server.get("/hierarchy/types")
    for area, wanted in (("work/tree", lambda t: t in WORK), ("requirements", lambda t: t not in WORK)):
        open_app(page, area=area)
        for type_id in types:
            target = page.get_by_test_id(f"quick-{type_id}")
            expect(target).to_be_visible() if wanted(type_id) else expect(target).to_have_count(0)


def test_a_template_card_creates_the_item_and_shows_it(page):
    templates = page.server.get("/templates")
    assert templates, "the agile flavour ships templates"
    kind = (templates[0].get("fields") or {}).get("req_type", "functional")
    open_app(page, area="work/tree" if kind in WORK else "requirements")
    card = page.get_by_test_id(f"template-{templates[0]['id']}")
    card.click()
    items = wait_until(lambda: page.server.get("/requirements"), what="the item made from the template")
    assert len(items) == 1
    expect(page.locator(".tree-node").first).to_be_visible()
    expect(page.get_by_role("button", name="Save & Commit")).to_be_visible()
