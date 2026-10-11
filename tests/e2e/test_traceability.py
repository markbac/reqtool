"""The per-item Insight tab, impact preview, suspect links, reviews and approvals."""

import pytest
from playwright.sync_api import expect

from .helpers import expand, field, open_app, seed_tree, select_item, tree_node


def open_insight(page, node_id: str):
    select_item(page, node_id)
    page.get_by_role("button", name="Trace, Progress & Quality").click()
    return page.get_by_role("heading", name="Traceability")


def link_story_to_epic(server, ids):
    """Make the story depend on the epic with a real relationship (a parent link is not one)."""
    story = server.get(f"/requirements/{ids['story']['uid']}")
    server.put(f"/requirements/{ids['story']['uid']}",
               {**story, "relationships": [{"type": "satisfies", "target": {"uid": ids["epic"]["uid"]}}]})


def test_insight_shows_children_gaps_and_lifecycle(page):
    seed_tree(page.server)
    open_app(page)
    expand(page, "TH-001", "IN-001")
    open_insight(page, "EP-001")
    expect(page.get_by_role("heading", name="Lifecycle")).to_be_visible()
    expect(page.get_by_text("Downstream (1)")).to_be_visible()
    expect(page.locator(".ins-row", has_text="US-001")).to_be_visible()
    expect(page.get_by_text("Gaps:")).to_contain_text("not_verified")
    expect(page.get_by_text("Upstream (0)")).to_be_visible()


def test_insight_follows_relationships_in_both_directions(page):
    ids = seed_tree(page.server)
    link_story_to_epic(page.server, ids)
    open_app(page)
    expand(page, "TH-001", "IN-001", "EP-001")
    open_insight(page, "US-001")
    upstream = page.get_by_text("Upstream (1)")
    expect(upstream).to_be_visible()
    expect(page.locator(".ins-row", has_text="EP-001").first).to_be_visible()
    # clicking a linked item opens it
    page.locator(".ins-row", has_text="EP-001").first.click()
    expect(field(page, "Title")).to_have_value("Epic one")


def test_quality_findings_appear_and_clear_as_the_text_improves(page):
    ids = seed_tree(page.server)
    open_app(page)
    expand(page, "TH-001", "IN-001", "EP-001")
    open_insight(page, "US-001")
    expect(page.locator(".ins-pill", has_text="Q002")).to_be_visible()
    # adding an acceptance criterion is advisory feedback that disappears once it is there
    page.server.put(f"/requirements/{ids['story']['uid']}", {
        **page.server.get(f"/requirements/{ids['story']['uid']}"),
        "acceptance_criteria": [{"text": "Given a user, when they log in, then they see the home page"}]})
    page.reload()
    page.locator("select.header-select").first.select_option("p1")
    expand(page, "TH-001", "IN-001", "EP-001")
    open_insight(page, "US-001")
    expect(page.get_by_role("heading", name="Writing quality (advisory)")).to_be_visible()
    expect(page.locator(".ins-pill", has_text="Q002")).to_have_count(0)


def test_request_review_lists_it_for_the_reviewer_and_in_the_inbox(page):
    ids = seed_tree(page.server)
    open_app(page)
    expand(page, "TH-001", "IN-001")
    open_insight(page, "EP-001")
    button = page.get_by_role("button", name="Request review")
    expect(button).to_be_disabled()
    page.get_by_label("Reviewers").fill("user, bob")
    button.click()
    expect(page.locator(".ins-row", has_text="bob")).to_be_visible()
    reviews = page.server.get(f"/requirements/{ids['epic']['uid']}/review-requests")
    assert sorted(r["reviewer"] for r in reviews) == ["bob", "user"]

    from .helpers import open_menu_item, panel, close_panel
    open_menu_item(page, "✉ Inbox")
    inbox = panel(page, "Inbox")
    expect(inbox.get_by_text("EP-001").first).to_be_visible()
    close_panel(page)


@pytest.mark.parametrize("server", ["defaults"], indirect=True)  # the formal workflow has an approved state
def test_approve_this_version_records_who_and_what(page):
    server = page.server
    server.post("/products", {"id": "p1", "title": "Product One"})
    req = server.req(title="The system shall log every login attempt", req_type="functional",
                     content={"description": "The system shall log every login attempt with a timestamp."})
    for state in ("in_review", "reviewed"):
        server.post(f"/requirements/{req['uid']}/transition", {"to_state": state}, expect=200)
    open_app(page)
    page.keyboard.press("Control+k")
    page.get_by_placeholder("Search", exact=False).last.fill("log every login")
    page.get_by_text(req["id"]).last.click()
    page.get_by_role("button", name="Trace, Progress & Quality").click()
    page.get_by_role("button", name="Approve this version").click()
    expect(page.get_by_text("Approved by").first).to_be_visible()
    approvals = server.get(f"/requirements/{req['uid']}/approvals")
    assert approvals["approvals"]
    assert approvals["current"]["status"] == "approved"
    assert approvals["current"]["signed_hash"] == approvals["current_hash"]


@pytest.mark.expect_http(409)
def test_approving_where_the_workflow_forbids_it_explains_why(page):
    seed_tree(page.server)
    open_app(page)
    expand(page, "TH-001", "IN-001", "EP-001")
    open_insight(page, "US-001")
    page.get_by_role("button", name="Approve this version").click()
    expect(page.locator(".toast-error").last).to_contain_text("not permitted")


def test_saving_a_change_with_dependants_asks_first_and_can_be_cancelled(page):
    ids = seed_tree(page.server)
    link_story_to_epic(page.server, ids)
    open_app(page)
    expand(page, "TH-001", "IN-001")
    select_item(page, "EP-001")
    messages = []
    answer = {"accept": False}
    page.on("dialog", lambda d: (messages.append(d.message), d.accept() if answer["accept"] else d.dismiss()))

    field(page, "Title").fill("Epic one, reworded")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_role("button", name="Save", exact=True)).to_be_enabled()
    assert messages and "US-001" in messages[0] and "suspect" in messages[0]
    assert page.server.get(f"/requirements/{ids['epic']['uid']}")["title"] == "Epic one"  # nothing was saved

    answer["accept"] = True
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_role("button", name="Saved ✓")).to_be_visible()
    assert page.server.get(f"/requirements/{ids['epic']['uid']}")["title"] == "Epic one, reworded"
    flagged = page.server.get(f"/requirements/{ids['story']['uid']}")["relationships"][0]
    assert flagged.get("suspect") is True


def test_suspect_link_shows_in_the_tree_and_can_be_cleared(page):
    ids = seed_tree(page.server)
    link_story_to_epic(page.server, ids)
    epic = page.server.get(f"/requirements/{ids['epic']['uid']}")
    page.server.put(f"/requirements/{ids['epic']['uid']}", {**epic, "title": "Epic one changed"})
    open_app(page)
    expand(page, "TH-001", "IN-001", "EP-001")
    expect(tree_node(page, "US-001").locator(".tree-node-suspect")).to_contain_text("1")
    select_item(page, "US-001")
    page.get_by_role("button", name="Relationships & Links").click()
    expect(page.get_by_text("suspect").first).to_be_visible()
    page.get_by_role("button", name="Clear suspect").first.click()
    expect(tree_node(page, "US-001").locator(".tree-node-suspect")).to_have_count(0)
    assert not page.server.get(f"/requirements/{ids['story']['uid']}")["relationships"][0].get("suspect")


def test_strategic_item_shows_a_summary_and_progress_in_the_tree(page):
    ids = seed_tree(page.server)
    page.server.post(f"/requirements/{ids['story']['uid']}/transition", {"to": "ready"}, expect=None)
    open_app(page)
    expect(tree_node(page, "TH-001").get_by_role("progressbar")).to_be_visible()
    open_insight(page, "TH-001")
    expect(page.get_by_text("Complete").first).to_be_visible()
    expect(page.get_by_text("Items below").first).to_be_visible()
