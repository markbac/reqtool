"""Workflow editor, the transition pop-up, the writing check and role-based screens, in a real browser."""

import pytest
from playwright.sync_api import expect
from ruamel.yaml import YAML

from .helpers import open_app, open_menu_item, panel, select_item

DEFAULTS = pytest.mark.parametrize("server", ["defaults"], indirect=True)


def hierarchy(server) -> dict:
    return YAML(typ="safe").load((server.root / ".reqtool" / "hierarchy.yaml").read_text(encoding="utf-8"))


def show(page, item: dict) -> None:
    """Put ``item`` at the top of product p1 and open it in the editor."""
    server = page.server
    if not any(p["id"] == "p1" for p in server.get("/products")):
        server.post("/products", {"id": "p1", "title": "Product One"})
    server.put("/products/p1", {"root_requirements": [{"uid": item["uid"]}]}, expect=None)
    open_app(page)
    select_item(page, item["id"])


@DEFAULTS
def test_workflow_editor_changes_a_guard_draws_the_diagram_and_writes_the_repo_file(page):
    open_app(page)
    open_menu_item(page, "⬡ Workflows")
    p = panel(page, "Workflows")
    p.get_by_label("Workflow", exact=True).select_option("formal")
    expect(p.get_by_test_id("mermaid-diagram").locator("svg")).to_be_visible()  # drawn from the server's Mermaid
    p.get_by_role("button", name="in_review needs").click()  # open what a move into in_review needs
    p.get_by_label("Rationale").check()
    p.get_by_role("button", name="Save", exact=True).click()
    expect(page.locator(".toast", has_text="Workflow saved")).to_be_visible()
    assert hierarchy(page.server)["workflows"]["formal"]["guards"]["in_review"]["requires_fields"] == ["content.rationale"]
    uid = page.server.req(title="Pump", req_type="functional")["uid"]
    page.server.put(f"/requirements/{uid}", {"status": "in_review"}, expect=409)  # the new rule is enforced at once


@DEFAULTS
def test_workflow_editor_adds_a_state_with_a_move(page):
    open_app(page)
    open_menu_item(page, "⬡ Workflows")
    p = panel(page, "Workflows")
    p.get_by_label("Workflow", exact=True).select_option("formal")
    p.get_by_label("New state id").fill("parked")
    p.get_by_role("button", name="Add state").click()
    p.get_by_label("approved to parked").check()
    p.get_by_label("parked to draft").check()
    p.get_by_role("button", name="Save", exact=True).click()
    expect(page.locator(".toast", has_text="Workflow saved")).to_be_visible()
    saved = hierarchy(page.server)["workflows"]["formal"]
    assert "parked" in [s["id"] for s in saved["states"]]
    assert "parked" in saved["transitions"]["approved"] and saved["transitions"]["parked"] == ["draft"]


@DEFAULTS
@pytest.mark.expect_http(409)
def test_the_transition_pop_up_asks_for_missing_data_and_saves_the_move(page):
    server = page.server
    item = server.req(title="Brake", req_type="safety", content={"description": "The brake shall stop the car."})
    uid = item["uid"]
    server.put(f"/requirements/{uid}", {"status": "in_review"})
    server.put(f"/requirements/{uid}", {"status": "reviewed"})
    show(page, item)
    page.get_by_role("button", name="Approved", exact=True).click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("Move to Approved")
    expect(dialog).to_contain_text("Safety requirements must have")
    expect(dialog.get_by_role("button", name="Apply and save")).to_be_disabled()
    dialog.get_by_label("Rationale").fill("A failed brake is a hazard")
    dialog.get_by_label("Safety classification").fill("ASIL-B")
    dialog.get_by_label("New acceptance criterion").fill("Stops from 100 km/h in under 40 m")
    dialog.get_by_role("button", name="Add", exact=True).click()
    dialog.get_by_role("button", name="Change other fields").click()
    dialog.get_by_label("Owner").fill("alice")  # any field can be changed while moving on
    dialog.get_by_role("button", name="Apply and save").click()
    expect(page.locator(".toast", has_text="Saved")).to_be_visible()
    expect(page.locator(".wf-current-state", has_text="Approved")).to_be_visible()
    saved = server.get(f"/requirements/{uid}")
    assert saved["status"] == "approved" and saved["owner"] == "alice"
    assert saved["content"]["rationale"] == "A failed brake is a hazard" and saved["safety_classification"] == "ASIL-B"


@DEFAULTS
def test_a_move_with_nothing_missing_needs_no_pop_up(page):
    item = page.server.req(title="Pump", req_type="functional")
    uid = item["uid"]
    show(page, item)
    page.get_by_role("button", name="In Review", exact=True).click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.locator(".toast", has_text="Saved")).to_be_visible()
    expect(page.locator(".wf-current-state", has_text="In Review")).to_be_visible()
    assert page.server.get(f"/requirements/{uid}")["status"] == "in_review"


@DEFAULTS
def test_pop_up_cancel_leaves_the_item_alone(page):
    server = page.server
    item = server.req(title="Brake", req_type="safety")
    uid = item["uid"]
    server.put(f"/requirements/{uid}", {"status": "in_review"})
    server.put(f"/requirements/{uid}", {"status": "reviewed"})
    show(page, item)
    page.get_by_role("button", name="Approved", exact=True).click()
    page.get_by_role("dialog").get_by_role("button", name="Cancel").click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    assert server.get(f"/requirements/{uid}")["status"] == "reviewed"


@DEFAULTS
def test_writing_check_lists_findings_and_an_admin_changes_the_settings(page):
    server = page.server
    uid = server.req(title="Pump", req_type="functional",
                     content={"description": "In order to run, the pump shall be fast."})["uid"]
    open_app(page)
    open_menu_item(page, "✎ Writing check")
    p = panel(page, "Writing check")
    expect(p.get_by_test_id("wc-summary")).to_contain_text("finding")
    expect(p).to_contain_text("DOC002")
    expect(p).to_contain_text("REQ001")
    p.get_by_role("button", name="Settings", exact=True).click()
    p.get_by_label("Severity of DOC002").select_option("error")
    p.get_by_role("button", name="Save settings").click()
    expect(page.locator(".toast", has_text="Writing check settings saved")).to_be_visible()
    saved = YAML(typ="safe").load((server.root / ".reqtool" / "lint.yaml").read_text(encoding="utf-8"))
    assert saved["severities"]["DOC002"] == "error" and "vale" in saved
    assert server.get(f"/requirements/{uid}/lint")["issues"][0]["severity"] in ("error", "warning")


@DEFAULTS
def test_the_item_editor_shows_its_writing_suggestions(page):
    item = page.server.req(title="Pump", req_type="functional",
                           content={"description": "The pump shall run in order to cool."})
    show(page, item)
    strip = page.get_by_test_id("writing-strip")
    expect(strip).to_contain_text("writing suggestion")
    strip.get_by_role("button").click()
    expect(strip).to_contain_text("Redundant phrase")
