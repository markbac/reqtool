"""Issue intake in the browser: an issue is triaged as a defect and the defect is raised from it."""

from playwright.sync_api import expect

from .helpers import open_app, wait_until

DESC = "Pressing Save does nothing."


def open_issue(page, issue):
    page.keyboard.press("Control+k")
    page.get_by_placeholder("Search", exact=False).last.fill(issue["title"])
    page.get_by_text(issue["id"]).last.click()


def test_triage_an_issue_as_a_defect_and_raise_it(page):
    issue = page.server.req(title="Save button does nothing", req_type="issue", content={"description": DESC})
    open_app(page)
    open_issue(page, issue)

    # Reported -> In triage: someone has to own it, so the pop-up asks for an assignee.
    page.get_by_role("button", name="In triage", exact=True).click()
    dialog = page.get_by_role("dialog", name="Move to In triage")
    dialog.get_by_label("Assignee").fill("tess")
    dialog.get_by_role("button", name="Apply and save").click()
    wait_until(lambda: page.server.get(f"/requirements/{issue['uid']}")["status"] == "in_triage", what="triage to start")

    # In triage -> Defect: it needs a priority and a note on why.
    page.get_by_role("button", name="Defect", exact=True).click()
    dialog = page.get_by_role("dialog", name="Move to Defect")
    expect(dialog).to_contain_text("Say why this is a defect")
    dialog.get_by_label("Triage note").fill("Reproduced on 1.2")
    dialog.get_by_label("Priority").select_option("high")
    dialog.get_by_role("button", name="Apply and save").click()
    wait_until(lambda: page.server.get(f"/requirements/{issue['uid']}")["status"] == "defect", what="the decision")

    # The defect is raised from the issue and opened.
    page.get_by_role("button", name="Raise a defect").click()
    wait_until(lambda: any(r["req_type"] == "bug" for r in page.server.get("/requirements")), what="the defect")
    made = page.server.get(f"/requirements/{next(r for r in page.server.get('/requirements') if r['req_type'] == 'bug')['uid']}")
    assert made["title"] == "Save button does nothing" and made["relationships"][0]["type"] == "derived_from"
