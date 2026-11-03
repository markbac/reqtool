"""Issue intake in the browser (#379): an issue is triaged on Work > Issues and converted into a defect."""

from playwright.sync_api import expect

from .helpers import open_app, wait_until

DESC = "Pressing Save does nothing."


def test_triage_an_issue_and_make_it_a_defect(page):
    issue = page.server.req(title="Save button does nothing", req_type="issue", content={"description": DESC})
    req = page.server.req(title="Save stores the file", req_type="functional", content={"description": "The app shall save."})
    open_app(page, area="work/issues")
    expect(page.get_by_role("navigation", name="Main").get_by_label("1 issues to triage")).to_be_visible()

    page.locator(".work-row", has_text=issue["id"]).click()
    page.get_by_role("button", name="Start triage").click()
    wait_until(lambda: page.server.get(f"/requirements/{issue['uid']}")["status"] == "in_triage", what="triage to start")

    page.get_by_role("button", name="Make it a defect").first.click()
    form = page.locator(".issue-panel")
    form.get_by_placeholder("Search by id or title").first.fill(req["id"])
    form.get_by_role("option", name=req["id"]).click()
    form.get_by_label("Triage note").fill("Reproduced on 1.2")
    form.get_by_role("button", name="Make it a defect").click()

    wait_until(lambda: page.server.get(f"/requirements/{issue['uid']}")["req_type"] == "bug", what="the conversion")
    bug = page.server.get(f"/requirements/{issue['uid']}")
    assert bug["id"].startswith("BG-") and issue["id"] in bug["aliases"]
    assert bug["relationships"][-1]["target"]["uid"] == req["uid"]
    expect(page).to_have_url(f"{page.server.url}/#/work/backlog?item={issue['uid']}&product=p1")


def test_reject_an_issue_as_a_duplicate(page):
    issue = page.server.req(title="Duplicate report", req_type="issue", content={"description": DESC})
    page.server.put(f"/requirements/{issue['uid']}", {"assignee": "tess"})
    page.server.post(f"/requirements/{issue['uid']}/transition", {"to_state": "in_triage"}, expect=200)
    open_app(page, area="work/issues")
    page.locator(".work-row", has_text=issue["id"]).click()
    page.get_by_role("button", name="Reject").first.click()
    form = page.locator(".issue-panel")
    form.get_by_label("Reason").select_option("duplicate")
    form.get_by_label("Duplicate of").fill("ISS-001")
    form.get_by_label("Triage note").fill("Same as the first report")
    form.get_by_role("button", name="Reject").click()
    wait_until(lambda: page.server.get(f"/requirements/{issue['uid']}")["status"] == "duplicate", what="the rejection")
    page.get_by_role("tab", name="Rejected").click()
    expect(page.locator(".work-row", has_text=issue["id"])).to_be_visible()
