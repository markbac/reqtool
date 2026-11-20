"""The application shell: it loads cleanly offline, and the header actions, theme, help and search work."""

from playwright.sync_api import expect

from .helpers import close_panel, open_app, open_menu_item, panel, seed_tree


def test_loads_cleanly_and_lists_products(page):
    page.server.post("/products", {"id": "p1", "title": "Product One"})
    page.server.post("/products", {"id": "p2", "title": "Product Two"})
    open_app(page, product=None)
    expect(page.locator(".header-brand-name")).to_have_text("reqtool")
    expect(page.locator("select.header-select").first.locator("option")).to_have_text(
        ["Choose a product", "Product One", "Product Two"])
    expect(page.get_by_text("Choose a product").last).to_be_visible()
    expect(page.get_by_text("QUICK CREATE")).to_be_visible()


def test_a_single_product_is_selected_automatically(page):
    page.server.post("/products", {"id": "p1", "title": "Product One"})
    open_app(page, product=None)
    expect(page.locator("select.header-select").first).to_have_value("p1")


def test_selecting_a_product_shows_its_tree(page):
    seed_tree(page.server)
    open_app(page)
    expect(page.locator(".tree-node", has_text="TH-001")).to_be_visible()
    expect(page.locator(".sidebar-empty", has_text="Choose a product")).to_have_count(0)


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
    page.get_by_role("button", name="Help").click()
    expect(page.get_by_text("About").first).to_be_visible()
    page.keyboard.press("Escape")


def test_validate_and_export_open_as_drawers_and_metrics_is_on_insights(page):
    seed_tree(page.server)
    open_app(page, area="requirements")
    page.get_by_role("button", name="Validate").click()
    panel(page, "Validation")
    close_panel(page)
    page.get_by_role("button", name="Export").click()
    p = panel(page, "Export")
    expect(p.get_by_text("Audit Package").first).to_be_visible()
    close_panel(page)
    open_menu_item(page, "◔ Overview & release gate")
    expect(page.get_by_text("Approval funnel")).to_be_visible()


def test_filter_tree_narrows_the_visible_items(page):
    ids = seed_tree(page.server)
    open_app(page)
    page.get_by_label("Filter the tree").fill("Epic one")
    expect(page.locator(".tree-node", has_text=ids["epic"]["id"])).to_be_visible()
    page.get_by_label("Filter the tree").fill("zzz-no-such-item")
    expect(page.locator(".tree-node")).to_have_count(0)


def test_command_palette_finds_an_item_and_a_page(page):
    ids = seed_tree(page.server)
    open_app(page)
    page.keyboard.press("Control+k")
    box = page.get_by_placeholder("Search", exact=False).last
    box.fill("Epic one")
    page.get_by_text(ids["epic"]["id"]).last.click()
    expect(page.get_by_role("button", name="Save & Commit")).to_be_visible()
    page.keyboard.press("Control+k")
    page.get_by_placeholder("Search", exact=False).last.fill("templ")
    page.get_by_text("Settings: templates").click()
    expect(page).to_have_url(f"{page.server.url}/#/settings/templates?product=p1")


def test_the_menu_reaches_every_area_and_back_returns(page):
    open_app(page, product=None, area="")
    nav = page.get_by_role("navigation", name="Main")
    for name, path in (("Work", "work"), ("Decisions", "decisions"), ("Principles", "principles"),
                       ("Insights", "insights"), ("Settings", "settings"), ("Requirements", "requirements")):
        nav.get_by_role("link", name=name).first.click()
        expect(page.locator("h1.page-title")).to_have_text(name)
        expect(page).to_have_url(f"{page.server.url}/#/{path}")
    page.go_back()
    expect(page.locator("h1.page-title")).to_have_text("Settings")
    page.reload()
    expect(page.locator("h1.page-title")).to_have_text("Settings")
    expect(page.get_by_role("button", name="⋯ More")).to_have_count(0)


def test_the_product_is_remembered_and_an_old_link_still_opens_the_item(page):
    ids = seed_tree(page.server)
    open_app(page)
    page.goto(page.server.url)
    expect(page.locator("select.header-select").first).to_have_value("p1")
    page.goto(f"{page.server.url}/?uid={ids['story']['uid']}&type=requirement")
    expect(page.locator(".editor-id")).to_contain_text(ids["story"]["id"])
    expect(page).to_have_url(f"{page.server.url}/#/requirements?item={ids['story']['uid']}&product=p1")
