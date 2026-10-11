"""The application shell: it loads cleanly offline, and the header actions, theme, help and search work."""

from playwright.sync_api import expect

from .helpers import close_panel, open_app, open_menu_item, panel, seed_tree


def test_loads_cleanly_and_lists_products(page):
    page.server.post("/products", {"id": "p1", "title": "Product One"})
    page.server.post("/products", {"id": "p2", "title": "Product Two"})
    open_app(page, product=None)
    expect(page.locator(".header-brand-name")).to_have_text("reqtool")
    expect(page.locator("select.header-select").first.locator("option")).to_have_text(
        ["— select product —", "Product One", "Product Two"])
    expect(page.get_by_text("No product selected")).to_be_visible()
    expect(page.get_by_text("QUICK CREATE")).to_be_visible()


def test_a_single_product_is_selected_automatically(page):
    page.server.post("/products", {"id": "p1", "title": "Product One"})
    open_app(page, product=None)
    expect(page.locator("select.header-select").first).to_have_value("p1")


def test_selecting_a_product_shows_its_tree(page):
    seed_tree(page.server)
    open_app(page)
    expect(page.locator(".tree-node", has_text="TH-001")).to_be_visible()
    expect(page.get_by_text("No product selected")).to_have_count(0)


def test_theme_toggle_switches_and_persists_across_reload(page):
    open_app(page, product=None)
    html = page.locator("html")
    expect(html).to_have_attribute("data-theme", "dark")  # the default, set once start-up data has loaded
    page.locator("button[title^='Switch to']").click()
    expect(html).to_have_attribute("data-theme", "light")
    page.reload()
    expect(html).to_have_attribute("data-theme", "light")


def test_help_opens_and_closes(page):
    open_app(page, product=None)
    page.get_by_role("button", name="?", exact=True).click()
    expect(page.get_by_text("About").first).to_be_visible()
    page.keyboard.press("Escape")


def test_validate_metrics_and_export_panels_open(page):
    seed_tree(page.server)
    open_app(page)
    page.get_by_role("button", name="✓ Validate").click()
    panel(page, "Validation")
    close_panel(page)
    page.get_by_role("button", name="⊕ Metrics").click()
    expect(page.locator(".side-panel").first).to_be_visible()
    close_panel(page)
    page.get_by_role("button", name="↓ Export").click()
    p = panel(page, "Export")
    expect(p.get_by_text("Audit Package").first).to_be_visible()
    close_panel(page)


def test_filter_tree_narrows_the_visible_items(page):
    ids = seed_tree(page.server)
    open_app(page)
    page.get_by_placeholder("Filter tree…").fill("Epic one")
    expect(page.locator(".tree-node", has_text=ids["epic"]["id"])).to_be_visible()
    page.get_by_placeholder("Filter tree…").fill("zzz-no-such-item")
    expect(page.locator(".tree-node")).to_have_count(0)


def test_command_palette_finds_an_item(page):
    ids = seed_tree(page.server)
    open_app(page)
    page.keyboard.press("Control+k")
    box = page.get_by_placeholder("Search", exact=False).last
    box.fill("Epic one")
    page.get_by_text(ids["epic"]["id"]).last.click()
    expect(page.get_by_role("button", name="Save & Commit")).to_be_visible()


def test_overflow_menu_lists_the_insight_panels(page):
    open_app(page, product=None)
    page.get_by_role("button", name="⋯ More").click()
    for label in ("◔ Overview & release gate", "⇢ Roadmap", "⚖ Decisions & ADRs", "▦ Modules", "⎇ Change sets",
                  "✉ Inbox", "⌕ Query & saved views", "◎ Baselines", "⊗ Traceability"):
        expect(page.get_by_role("button", name=label)).to_be_visible()
    page.keyboard.press("Escape")
    page.mouse.click(5, 400)  # click away closes the menu
    open_menu_item(page, "⇢ Roadmap")
    panel(page, "Roadmap")
