"""Small helpers shared by the browser tests. They talk to the UI the way a person does (roles, labels, text)."""

from __future__ import annotations

from playwright.sync_api import Page, expect

CURRENT_PAGE: list = []  # set by the ``page`` fixture

DESCRIPTION = "The system shall record every change made to a requirement."


def open_app(page: Page, product: str | None = "p1", title: str = "Product One") -> None:
    """Load the UI and select a product, creating it through the API first when it does not exist."""
    server = page.server  # type: ignore[attr-defined]
    if product and not any(p["id"] == product for p in server.get("/products")):
        server.post("/products", {"id": product, "title": title})
    page.goto(server.url)
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


def open_menu_item(page: Page, label: str) -> None:
    page.get_by_role("button", name="⋯ More").click()
    page.get_by_role("menuitem", name=label).click()


def panel(page: Page, title: str):
    """The side panel whose heading is ``title`` (waits until it is shown)."""
    p = page.locator(".side-panel", has=page.locator(".side-panel-title", has_text=title)).first
    expect(p).to_be_visible()
    return p


def close_panel(page: Page) -> None:
    page.locator(".side-panel-header button", has_text="✕").first.click()
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
