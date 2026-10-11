"""The Views panel, the roadmap board and the traceability grid."""

from playwright.sync_api import expect

from .helpers import open_app, open_menu_item, panel, seed_tree, wait_until


def test_hierarchy_tree_collapses_and_opens_an_item(page):
    items = seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "◫ Views")
    p = panel(page, "Views")
    expect(p.get_by_role("treeitem")).to_have_count(4)
    p.get_by_role("button", name=f"Collapse {items['theme']['id']}").click()
    expect(p.get_by_role("treeitem")).to_have_count(1)
    p.get_by_role("button", name="Expand all").click()
    p.get_by_role("button", name="User story one", exact=False).click()
    expect(page.locator("input[value='User story one']").first).to_be_visible()


def test_coverage_has_a_table_and_a_legend(page):
    seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "◫ Views")
    p = panel(page, "Views")
    p.get_by_role("tab", name="Coverage").click()
    expect(p.get_by_label("Legend")).to_be_visible()
    expect(p.get_by_test_id("coverage-cell").first).to_be_visible()
    p.get_by_role("button", name="Show table").click()
    expect(p.get_by_test_id("coverage-table")).to_contain_text("User story one")


def test_flow_and_ageing_and_principles_answer_when_empty_or_full(page):
    seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "◫ Views")
    p = panel(page, "Views")
    p.get_by_role("tab", name="Flow").click()
    expect(p.locator("[data-testid^='flow-']").first).to_be_visible()
    p.get_by_role("tab", name="Decision ageing").click()
    expect(p.get_by_test_id("view-empty")).to_contain_text("No open decisions")
    p.get_by_role("tab", name="Burn-up").click()
    expect(p.get_by_test_id("view-empty")).to_contain_text("No items in this iteration")


def test_roadmap_board_moves_a_card_to_another_release(page):
    items = seed_tree(page.server)
    page.server.put(f"/requirements/{items['initiative']['uid']}", {"target_release": "R1"})
    open_app(page)
    open_menu_item(page, "🗺 Roadmap")
    p = panel(page, "Roadmap")
    p.get_by_role("tab", name="Board").click()
    card = p.get_by_test_id(f"rb-card-{items['initiative']['id']}")
    expect(card).to_be_visible()
    card.get_by_role("combobox").select_option("unplanned")
    wait_until(lambda: not page.server.get(f"/requirements/{items['initiative']['uid']}").get("target_release"),
               what="the release to clear")


def test_traceability_grid_lists_gaps_and_downloads_csv(page):
    items = seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "⊗ Traceability")
    grid = page.get_by_test_id("trace-grid")
    expect(grid).to_contain_text(items["story"]["id"])
    expect(grid).to_contain_text("no link")
    grid.get_by_label("Only requirements with no link").check()
    expect(grid.get_by_role("status")).to_contain_text("without a link")
    with page.expect_download() as dl:
        grid.get_by_role("link", name="Download CSV").click()
    assert dl.value.suggested_filename.endswith(".csv")
