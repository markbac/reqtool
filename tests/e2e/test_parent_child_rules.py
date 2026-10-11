"""#341 in the browser: the board's drag-and-drop with roll-up, a blocked move forced with a reason, and the rule editor."""

import pytest
from playwright.sync_api import expect

from .helpers import open_app, seed_tree, wait_until
from .test_kanban import column, open_board
from .helpers import drag_and_drop


def set_rules(server, checks, changes):
    from reqtool import workflow_rules
    server.put("/rules", workflow_rules.default_rules(checks, changes))


def status(server, item):
    return server.get(f"/requirements/{item['uid']}")["status"]


def test_dragging_a_story_starts_its_epic_in_auto_mode(page):
    ids = seed_tree(page.server)
    set_rules(page.server, "off", "auto")
    open_app(page)
    open_board(page)
    drag_and_drop(page, column(page, "backlog").locator(".kanban-card", has_text="US-001"), column(page, "in progress"))
    wait_until(lambda: status(page.server, ids["epic"]) == "in_progress", what="the epic to be rolled up")
    expect(column(page, "in progress").locator(".kanban-card", has_text="EP-001")).to_have_count(1)


def test_suggest_mode_asks_before_moving_the_epic(page):
    ids = seed_tree(page.server)
    set_rules(page.server, "off", "suggest")
    open_app(page)
    open_board(page)
    drag_and_drop(page, column(page, "backlog").locator(".kanban-card", has_text="US-001"), column(page, "in progress"))
    dialog = page.get_by_role("dialog", name="Suggested follow-up moves")
    expect(dialog).to_contain_text("EP-001")
    assert status(page.server, ids["epic"]) == "backlog"
    dialog.get_by_role("button", name="Move selected").click()
    wait_until(lambda: status(page.server, ids["epic"]) == "in_progress", what="the accepted suggestion")


@pytest.mark.expect_http(409)
def test_a_blocked_drop_can_be_forced_with_a_reason(page):
    ids = seed_tree(page.server)
    page.server.call("POST", f"/requirements/{ids['epic']['uid']}/transition", {"to_state": "cancelled"}, expect=200)
    set_rules(page.server, "error", "off")
    open_app(page)
    open_board(page)
    drag_and_drop(page, column(page, "backlog").locator(".kanban-card", has_text="US-001"), column(page, "in progress"))
    dialog = page.get_by_role("dialog", name="Move blocked by a rule")
    expect(dialog).to_contain_text("No work under a closed parent")
    assert status(page.server, ids["story"]) == "backlog"
    force = dialog.get_by_role("button", name="Force anyway")
    expect(force).to_be_disabled()
    dialog.get_by_label("Reason for forcing it").fill("Customer escalation")
    force.click()
    wait_until(lambda: status(page.server, ids["story"]) == "in_progress", what="the forced move")
    forced = page.server.get("/rules/overrides")["overrides"]
    assert forced[0]["reason"] == "Customer escalation"


def test_the_workflow_editor_changes_and_saves_a_rule(page):
    set_rules(page.server, "warn", "suggest")
    open_app(page)
    page.get_by_role("button", name="⋯ More").click()
    page.get_by_text("Workflows", exact=False).first.click()
    mode = page.get_by_label("Mode for no-start-under-closed")
    expect(mode).to_have_value("warn")
    mode.select_option("error")
    page.get_by_role("button", name="Save rules").click()
    wait_until(lambda: next(r for r in page.server.get("/rules")["rules"]
                            if r["id"] == "no-start-under-closed")["mode"] == "error", what="the rule to be saved")
