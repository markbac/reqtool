"""The task board: columns, strategic items kept off it, filters, drag and drop, creating cards."""

from playwright.sync_api import expect

from .helpers import drag_and_drop, open_app, seed_tree, wait_until


def open_board(page):
    page.get_by_text("TASK MGMT").click()
    expect(page.locator(".kanban-page")).to_be_visible()


def column(page, name: str):
    """The board column labelled ``name`` (for example ``ready`` or ``in progress``)."""
    return page.locator(".kanban-col", has=page.locator(".kanban-col-label", has_text=name)).first


def test_board_shows_delivery_items_but_not_themes_or_initiatives(page):
    seed_tree(page.server)
    open_app(page)
    open_board(page)
    body = page.locator("body")
    expect(body).to_contain_text("EP-001")
    expect(body).to_contain_text("US-001")
    expect(body).not_to_contain_text("TH-001")
    expect(page.locator(".kanban-card", has_text="Initiative one")).to_have_count(0)   # shown only as a parent, never as a card
    expect(page.get_by_text("SPRINT SNAPSHOT")).to_be_visible()


def test_cards_land_in_the_column_of_their_status(page):
    ids = seed_tree(page.server)
    story = page.server.get(f"/requirements/{ids['story']['uid']}")
    page.server.put(f"/requirements/{ids['story']['uid']}", {**story, "status": "in_progress"})
    open_app(page)
    open_board(page)
    expect(column(page, "in progress").locator(".kanban-card", has_text="US-001")).to_have_count(1)
    expect(column(page, "backlog").locator(".kanban-card", has_text="US-001")).to_have_count(0)
    expect(column(page, "backlog").locator(".kanban-card", has_text="EP-001")).to_have_count(1)


def test_dragging_a_card_changes_its_status(page):
    ids = seed_tree(page.server)
    open_app(page)
    open_board(page)
    card = column(page, "backlog").locator(".kanban-card", has_text="US-001")
    drag_and_drop(page, card, column(page, "ready"))
    expect(column(page, "ready").locator(".kanban-card", has_text="US-001")).to_have_count(1)
    wait_until(lambda: page.server.get(f"/requirements/{ids['story']['uid']}")["status"] == "ready", what="the move to be saved")
    page.reload()
    page.locator("select.header-select").first.select_option("p1")
    open_board(page)
    expect(column(page, "ready").locator(".kanban-card", has_text="US-001")).to_have_count(1)


def test_type_filter_narrows_the_board(page):
    seed_tree(page.server)
    open_app(page)
    open_board(page)
    page.locator("select", has=page.locator("option", has_text="All types")).first.select_option(label="Epic")
    body = page.locator("body")
    expect(body).to_contain_text("EP-001")
    expect(body).not_to_contain_text("US-001")


def test_clicking_a_card_opens_the_editor(page):
    seed_tree(page.server)
    open_app(page)
    open_board(page)
    page.locator(".kanban-card", has_text="US-001").click()
    expect(page.get_by_role("button", name="Save & Commit")).to_be_visible()


def test_new_card_is_created_from_the_board(page):
    open_app(page)
    open_board(page)
    page.get_by_role("button", name="+ New").last.click()
    expect(page.locator(".toast-success").last).to_contain_text("Created")
    assert [r["req_type"] for r in page.server.get("/requirements")] == ["story"]


def test_unknown_status_gets_an_uncolumned_lane(page):
    ids = seed_tree(page.server)
    # a status that no workflow knows about, e.g. left behind by a hand edit
    import re
    path = page.server.root / "requirements" / f"{ids['story']['uid']}.yaml"
    path.write_text(re.sub(r"(?m)^status: .*$", "status: mystery", path.read_text()))
    wait_until(lambda: page.server.get(f"/requirements/{ids['story']['uid']}")["status"] == "mystery", what="the watcher")
    open_app(page)
    open_board(page)
    lane = column(page, "no matching column")
    expect(lane.locator(".kanban-card", has_text="US-001")).to_have_count(1)


def test_a_card_moves_from_its_menu_without_dragging(page):
    ids = seed_tree(page.server)
    open_app(page)
    open_board(page)
    card = column(page, "backlog").locator(".kanban-card", has_text="US-001")
    card.get_by_label("Move US-001 to").select_option("ready")
    wait_until(lambda: page.server.get(f"/requirements/{ids['story']['uid']}")["status"] == "ready", what="the menu move")


def test_a_guarded_move_opens_the_pop_up_and_cancelling_leaves_the_board_alone(page):
    issue = page.server.req(title="Save does nothing", req_type="issue", content={"description": "Nothing happens."})
    open_app(page)
    open_board(page)
    card = column(page, "reported").locator(".kanban-card", has_text=issue["id"])
    card.get_by_label(f"Move {issue['id']} to").select_option("in_triage")
    dialog = page.get_by_role("dialog", name="Move to In triage")
    dialog.get_by_role("button", name="Cancel").click()
    expect(column(page, "reported").locator(".kanban-card", has_text=issue["id"])).to_have_count(1)
    assert page.server.get(f"/requirements/{issue['uid']}")["status"] == "reported"

    card = column(page, "reported").locator(".kanban-card", has_text=issue["id"])
    card.get_by_label(f"Move {issue['id']} to").select_option("in_triage")
    dialog = page.get_by_role("dialog", name="Move to In triage")
    dialog.get_by_label("Assignee").fill("tess")
    dialog.get_by_role("button", name="Apply and save").click()
    wait_until(lambda: page.server.get(f"/requirements/{issue['uid']}")["status"] == "in_triage", what="the guarded move")
    expect(column(page, "in triage").locator(".kanban-card", has_text=issue["id"])).to_have_count(1)


def test_a_card_shows_its_parent_and_open_children(page):
    seed_tree(page.server)
    open_app(page)
    open_board(page)
    detail = column(page, "backlog").locator(".kanban-card", has=page.locator(".kanban-card-id", has_text="EP-001")).get_by_test_id("card-detail")
    expect(detail).to_contain_text("IN-001")
    expect(detail).to_contain_text("1 open")
