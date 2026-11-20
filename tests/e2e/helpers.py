"""Small helpers shared by the browser tests. They talk to the UI the way a person does (roles, labels, text)."""

from __future__ import annotations

from playwright.sync_api import Page, expect

CURRENT_PAGE: list = []  # set by the ``page`` fixture

DESCRIPTION = "The system shall record every change made to a requirement."


def open_app(page: Page, product: str | None = "p1", title: str = "Product One", area: str = "work/tree") -> None:
    """Load the UI on a page (by default Work > Tree, where ``seed_tree``'s theme to story hierarchy lives, #373)
    and select a product, creating it through the API first when it does not exist."""
    server = page.server  # type: ignore[attr-defined]
    if product and not any(p["id"] == product for p in server.get("/products")):
        server.post("/products", {"id": product, "title": title})
    page.goto(f"{server.url}/#/{area}" if area else server.url)
    expect(page.locator("header.header")).to_be_visible()
    if product:
        page.locator("select.header-select").first.select_option(product)


def seed_tree(server, product: str = "p1") -> dict:
    """Theme > initiative > epic > story, all described so they validate cleanly, attached to ``product``."""
    if not any(p["id"] == product for p in server.get("/products")):
        server.post("/products", {"id": product, "title": "Product One"})
    out: dict = {}
    parent = None
    for key, req_type, title in (("theme", "theme", "Theme alpha"), ("initiative", "initiative", "Initiative one"),
                                 ("epic", "epic", "Epic one"), ("story", "story", "User story one")):
        fields = {"title": title, "req_type": req_type, "content": {"description": DESCRIPTION}, "owner": "alice"}
        if parent:
            fields["parentId"] = parent["uid"]
        out[key] = parent = server.req(**fields)
    server.put(f"/products/{product}", {"root_requirements": [{"uid": out["theme"]["uid"]}]}, expect=None)
    return out


def tree_node(page: Page, text: str):
    return page.locator(".tree-node", has_text=text).first


def expand(page: Page, *ids: str) -> None:
    """Open the named tree nodes (they start collapsed)."""
    for node_id in ids:
        node = tree_node(page, node_id)
        if node.get_attribute("aria-expanded") == "false":
            node.locator(".tree-node-toggle").click()


def select_item(page: Page, node_id: str) -> None:
    tree_node(page, node_id).click()
    expect(page.get_by_role("button", name="Save & Commit")).to_be_visible()


def field(page: Page, label: str):
    """The input inside the editor field whose label is ``label``."""
    group = page.locator(".field-group", has=page.locator(".field-label", has_text=label)).first
    return group.locator("input:not([type=checkbox]), textarea, select").first


# Where each screen of the old More menu lives now (#373): a page (area, tab), or a drawer opened from a page or the
# header. Tests name the screen as before; this opens it the new way.
SCREENS = {
    "Overview & release gate": ("insights", "overview"), "Roadmap": ("work", "roadmap"), "Views": ("insights", "views"),
    "Coverage": ("insights", "coverage"), "Traceability": ("insights", "traceability"), "Decisions & ADRs": ("decisions", "records"),
    "Query & saved views": ("requirements", "table"), "Iterations & Gates": ("work", "iterations"),
    "Change sets": ("requirements", "changesets"), "Diagram Canvas": ("insights", "diagrams"),
    "Writing check": ("requirements", "writing"), "Duplicate Detector": ("requirements", "duplicates"),
    "Workflows": ("settings", "workflows"), "Vocabularies": ("settings", "vocabularies"),
    "Custom fields": ("settings", "fields"), "Templates": ("settings", "templates"),
    "Automation Rules": ("settings", "automation"), "Modules": ("requirements", "modules"),
    "Baselines": ("requirements", "baselines"), "Webhooks": ("settings", "webhooks"), "Repository": ("settings", "repository"),
}
DRAWERS = {"Inbox": "Inbox", "Login / Server": "Account", "Bulk update": "Bulk edit", "Import CSV": "Import"}


def go(page: Page, area: str, tab: str = "") -> None:
    """Open a page by clicking the left-hand menu and the page's tab, as a person would."""
    page.get_by_role("navigation", name="Main").get_by_role("link", name=_AREA_LABELS[area]).first.click()
    if not tab:
        return
    if (area, tab) in _TAB_LABELS:
        page.locator(".page-tabs").get_by_role("tab", name=_TAB_LABELS[(area, tab)], exact=True).click()
    else:  # a page reached from a page menu (Requirements > Check)
        page.evaluate(f"location.hash = '#/{area}/{tab}'")


_AREA_LABELS = {"requirements": "Requirements", "work": "Work", "decisions": "Decisions", "principles": "Principles",
                "insights": "Insights", "settings": "Settings"}
_TAB_LABELS = {("requirements", "tree"): "Tree", ("requirements", "table"): "Query", ("requirements", "modules"): "Modules",
               ("requirements", "baselines"): "Baselines", ("requirements", "changesets"): "Change sets",
               ("work", "issues"): "Issues", ("work", "backlog"): "Backlog", ("work", "tree"): "Tree", ("work", "board"): "Board",
               ("work", "roadmap"): "Roadmap", ("work", "iterations"): "Iterations",
               ("decisions", "records"): "Options and ADRs", ("principles", "library"): "Library", ("principles", "cited"): "Where cited",
               ("insights", "overview"): "Overview", ("insights", "coverage"): "Coverage",
               ("insights", "traceability"): "Traceability", ("insights", "views"): "Views", ("insights", "diagrams"): "Diagrams",
               ("settings", "workflows"): "Workflows", ("settings", "fields"): "Custom fields",
               ("settings", "vocabularies"): "Vocabularies", ("settings", "templates"): "Templates",
               ("settings", "automation"): "Automation", ("settings", "webhooks"): "Webhooks",
               ("settings", "writing"): "Writing check", ("settings", "repository"): "Repository"}


def open_menu_item(page: Page, label: str) -> None:
    """Open a screen that used to be in the More menu, given its old label (the icon is ignored)."""
    name = label.split(" ", 1)[1] if label[:1] and not label[:1].isalnum() else label
    if name in SCREENS:
        go(page, *SCREENS[name])
        return
    if name == "Inbox":
        page.get_by_role("button", name="Inbox").click()
    elif name == "Login / Server":
        page.get_by_role("button", name="Account").click()
    elif name == "Bulk update":
        go(page, "requirements", "tree")
        page.get_by_role("button", name="Bulk edit").first.click()
    elif name == "Import CSV":
        go(page, "requirements", "tree")
        page.get_by_role("button", name="Import").first.click()
    else:
        raise KeyError(f"no screen called {label!r}")


def panel(page: Page, title: str):
    """A screen by its title: a drawer whose heading is ``title``, or the page showing it (waits until shown)."""
    drawer = page.locator(".side-panel", has=page.locator(".side-panel-title", has_text=title))
    p = drawer.or_(page.locator("section.page-panel", has_text="").filter(
        has=page.locator(f'xpath=self::*[contains(translate(@aria-label, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
                         f'"abcdefghijklmnopqrstuvwxyz"), "{title.lower()}")]'))).first
    expect(p).to_be_visible()
    return p


def close_panel(page: Page) -> None:
    """Close the open drawer. A screen shown as a page (#374) has nothing to close."""
    if not page.locator(".side-panel").count():
        return
    page.locator(".side-panel-header button[aria-label='Close']").first.click()
    expect(page.locator(".side-panel")).to_have_count(0)


def toast_text(page: Page) -> str:
    return page.locator(".toast").last.inner_text()


def wait_until(check, timeout: float = 10.0, what: str = "condition"):
    """Poll ``check`` until it returns something truthy (for example after an edit made on disk)."""
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = check()
        if value:
            return value
        # Wait through Playwright, not time.sleep: the offline route handler and the dialog handlers run in
        # this thread, so a plain sleep would stop the page from making progress.
        if CURRENT_PAGE:
            CURRENT_PAGE[0].wait_for_timeout(200)
        else:
            time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {what}")


def drag_and_drop(page: Page, source, target) -> None:
    """HTML5 drag and drop, dispatched as events (Playwright's mouse drag does not drive it reliably)."""
    data = page.evaluate_handle("new DataTransfer()")
    source.dispatch_event("dragstart", {"dataTransfer": data})
    target.dispatch_event("dragover", {"dataTransfer": data})
    target.dispatch_event("drop", {"dataTransfer": data})
