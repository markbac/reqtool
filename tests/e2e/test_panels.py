"""The Insight panels reached from the header: overview, roadmap, decisions, modules, change sets, inbox, query,
baselines. Each is driven the way a person would and checked against what the server stored."""

import pytest
from playwright.sync_api import expect

from .helpers import close_panel, field, open_app, open_menu_item, panel, seed_tree

JUNIT = """<testsuite name="s" tests="2"><testcase classname="tests.TestLogin" name="US-001 login"/>
<testcase classname="tests.TestLogin" name="US-001 logout"><failure message="boom"/></testcase></testsuite>"""


def commit_all(server, message="seed"):
    server.git("add", "-A")
    server.git("commit", "-q", "-m", message)


def tab(p, name):
    p.get_by_role("tab", name=name).click()


# --- overview, release gate, coverage, health, test results, trend ---------------------

def test_overview_counts_and_percentages(page):
    seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "◔ Overview & release gate")
    p = panel(page, "Overview")
    expect(p.locator(".ins-stat", has_text="Requirements")).to_contain_text("4")
    expect(p.get_by_text("By status")).to_be_visible()
    expect(p.get_by_text("None yet")).to_be_visible()  # no baselines
    close_panel(page)


def test_release_gate_lists_findings_and_opens_the_item(page):
    ids = seed_tree(page.server)
    story = page.server.get(f"/requirements/{ids['story']['uid']}")
    page.server.put(f"/requirements/{ids['story']['uid']}", {**story, "safety_related": True})
    commit_all(page.server)  # uncommitted files are findings too: leave the substantive one
    open_app(page)
    open_menu_item(page, "◔ Overview & release gate")
    p = panel(page, "Overview")
    tab(p, "Release gate")
    expect(p.get_by_role("status").first).to_contain_text("1 finding(s) block the release")
    finding = p.locator(".ins-row", has_text="unverified_safety")
    expect(finding).to_contain_text("US-001")
    finding.click()  # opens the item and closes the panel
    expect(page.locator(".side-panel")).to_have_count(0)
    expect(field(page, "Title")).to_have_value("User story one")


def test_release_gate_is_ready_when_nothing_blocks(page):
    seed_tree(page.server)
    commit_all(page.server)
    open_app(page)
    open_menu_item(page, "◔ Overview & release gate")
    p = panel(page, "Overview")
    tab(p, "Release gate")
    expect(p.get_by_role("status").first).to_contain_text("Ready: no policy findings")


def test_coverage_tab_pairs_two_types(page):
    ids = seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "◔ Overview & release gate")
    p = panel(page, "Overview")
    tab(p, "Coverage")
    p.get_by_label("Source type").fill("epic")
    p.get_by_label("Target type").fill("story")
    expect(p.get_by_text("1 of 1 epic items have a story")).to_be_visible()
    expect(p.locator(".ins-pill.green", has_text="US-001")).to_be_visible()


def test_health_tab_runs_the_doctor(page):
    seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "◔ Overview & release gate")
    p = panel(page, "Overview")
    tab(p, "Health")
    assert page.server.get("/doctor")["ok"] is True
    expect(p.locator(".ins-pill").first).to_be_visible()


def test_uploading_junit_results_sets_verification(page, tmp_path):
    ids = seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "◔ Overview & release gate")
    p = panel(page, "Overview")
    tab(p, "Test results")
    f = tmp_path / "junit.xml"
    f.write_text(JUNIT)
    p.get_by_label("JUnit XML file").set_input_files(str(f))
    expect(p.get_by_role("status")).to_contain_text("2 test(s)")
    expect(p.get_by_role("status").locator(".ins-pill", has_text="failed")).to_be_visible()


@pytest.mark.expect_http(422)
def test_junit_with_an_entity_declaration_is_refused(page, tmp_path):
    seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "◔ Overview & release gate")
    p = panel(page, "Overview")
    tab(p, "Test results")
    f = tmp_path / "evil.xml"
    f.write_text('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><testsuite><testcase name="US-001"/></testsuite>')
    p.get_by_label("JUnit XML file").set_input_files(str(f))
    expect(p.get_by_role("alert")).to_be_visible()


def test_trend_tab_after_two_baselines(page):
    ids = seed_tree(page.server)
    commit_all(page.server)
    page.server.post("/baselines", {"name": "v1"})
    story = page.server.get(f"/requirements/{ids['story']['uid']}")
    page.server.put(f"/requirements/{ids['story']['uid']}", {**story, "title": "User story one, changed"})
    commit_all(page.server, "change")
    page.server.post("/baselines", {"name": "v2"})
    open_app(page)
    open_menu_item(page, "◔ Overview & release gate")
    p = panel(page, "Overview")
    tab(p, "Trend")
    expect(p.locator("tbody tr")).to_have_count(2)
    expect(p.locator("tbody tr").last).to_contain_text("~1")  # one changed item


# --- roadmap ------------------------------------------------------------------------------

def test_roadmap_nests_theme_initiative_epic_and_opens_items(page):
    seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "⇢ Roadmap")
    p = panel(page, "Roadmap")
    rows = p.locator(".ins-row")
    expect(rows).to_have_count(3)  # stories are delivery work, not roadmap items
    expect(rows.nth(0)).to_contain_text("TH-001")
    expect(rows.nth(2)).to_contain_text("EP-001")
    rows.nth(2).click()
    expect(field(page, "Title")).to_have_value("Epic one")


# --- decisions -----------------------------------------------------------------------------

def test_create_edit_and_export_a_decision(page):
    open_app(page, product=None)
    open_menu_item(page, "⚖ Decisions & ADRs")
    p = panel(page, "Decisions")
    p.get_by_role("button", name="+ New decision").click()
    p.get_by_label("Decision title").fill("Use PostgreSQL")
    p.get_by_label("Options").fill("PostgreSQL | + mature; relational | - heavier\nSQLite | + simple | - one writer")
    p.get_by_role("button", name="Save", exact=True).click()
    expect(p.locator(".ins-row", has_text="Use PostgreSQL")).to_be_visible()

    stored = page.server.get("/decisions")
    assert [d["title"] for d in stored] == ["Use PostgreSQL"]
    assert [o["name"] for o in stored[0]["content"]["options"]] == ["PostgreSQL", "SQLite"]

    p.get_by_role("button", name="Edit").click()
    p.get_by_label("Decision status").select_option("accepted")
    p.get_by_role("button", name="Save", exact=True).click()
    expect(p.locator(".ins-row", has_text="accepted")).to_be_visible()

    with page.expect_download() as dl:
        p.get_by_role("link", name="Export ADRs").click()
    assert dl.value.suggested_filename


def test_atam_fields_round_trip(page):
    open_app(page, product=None)
    open_menu_item(page, "⚖ Decisions & ADRs")
    p = panel(page, "Decisions")
    p.get_by_role("button", name="+ New decision").click()
    p.get_by_label("Decision title").fill("Message broker")
    p.get_by_label("ATAM analysis").check()
    p.get_by_label("Quality attributes (comma separated)").fill("latency, availability")
    p.get_by_label("Sensitivity points").fill("latency: broker hop count")
    p.get_by_label("Trade-off points").fill("latency+availability: replication adds delay")
    p.get_by_role("button", name="Save", exact=True).click()
    expect(p.locator(".ins-row", has_text="Message broker")).to_be_visible()
    atam = page.server.get("/decisions")[0]["content"]["atam"]
    assert atam["quality_attributes"] == ["latency", "availability"]
    assert atam["tradeoff_points"][0]["attributes"] == ["latency", "availability"]


def test_a_tbd_is_resolved_into_a_decision(page):
    tbd = page.server.post("/tbds", {"title": "Pick a queue", "content": {"description": "Undecided"}})
    open_app(page, product=None)
    open_menu_item(page, "⚖ Decisions & ADRs")
    p = panel(page, "Decisions")
    p.get_by_role("button", name="Resolve").click()
    page.get_by_role("dialog").get_by_role("textbox").first.fill("Use the managed queue")
    page.get_by_role("dialog").get_by_role("button", name="Resolve").click()
    expect(page.locator(".toast-success").last).to_contain_text("Resolved")
    assert page.server.get(f"/decisions/{tbd['uid']}")["status"] in ("resolved", "accepted")


# --- modules -------------------------------------------------------------------------------

def test_module_lifecycle_create_bump_clone_import(page):
    seed_tree(page.server)
    open_app(page)
    answers = iter(["safety-lib", "safety-lib-copy"])
    page.on("dialog", lambda d: d.accept(next(answers)))
    open_menu_item(page, "▦ Modules")
    p = panel(page, "Modules")
    p.get_by_role("button", name="+ New module").click()
    expect(p.get_by_role("heading", name="safety-lib")).to_be_visible()
    assert [m["id"] for m in page.server.get("/modules")] == ["safety-lib"]

    before = page.server.get("/modules/safety-lib")["manifest"]["version"]
    p.get_by_role("button", name="Bump minor").click()
    expect(page.locator(".toast-success").last).to_contain_text("Version bumped (minor)")
    after = page.server.get("/modules/safety-lib")["manifest"]["version"]
    assert after != before and after.split(".")[1] == str(int(before.split(".")[1]) + 1)
    expect(p.get_by_role("heading", name="safety-lib")).to_contain_text(f"v{after}")

    p.get_by_role("button", name="Clone").click()
    expect(page.locator(".toast-success").last).to_contain_text("cloned")
    assert sorted(m["id"] for m in page.server.get("/modules")) == ["safety-lib", "safety-lib-copy"]

    # a product must include a module before it can import it (the sidebar does that)
    close_panel(page)
    page.get_by_role("button", name="⊕ Module").click()
    page.locator(".module-include-item", has_text="safety-lib").first.get_by_role("button", name="⊕ Include").click()
    expect(page.locator(".toast-success").last).to_contain_text("included")

    open_menu_item(page, "▦ Modules")
    p = panel(page, "Modules")
    p.locator(".ins-clickable", has_text="safety-lib").first.click()
    p.get_by_role("button", name="Import into p1").click()
    expect(page.locator(".toast-success").last).to_contain_text("Imported")
    expect(p.get_by_text("locked 1.", exact=False).first).to_be_visible()
    p.get_by_role("button", name="Verify").click()
    expect(p.get_by_text("verified", exact=True)).to_be_visible()


# --- change sets ---------------------------------------------------------------------------

def test_change_set_start_review_and_merge(page):
    ids = seed_tree(page.server)
    commit_all(page.server)
    open_app(page)
    answers = iter(["spring-cleanup", "alice"])
    page.on("dialog", lambda d: d.accept(next(answers)))
    open_menu_item(page, "⎇ Change sets")
    p = panel(page, "Change sets")
    p.get_by_role("button", name="+ Start change set").click()
    row = p.locator(".ins-row", has_text="spring-cleanup")
    expect(row).to_contain_text("current")
    assert page.server.git("branch", "--show-current").startswith("changeset/")

    story = page.server.get(f"/requirements/{ids['story']['uid']}")
    page.server.put(f"/requirements/{ids['story']['uid']}", {**story, "title": "Story, edited in a change set"})
    commit_all(page.server, "edit on the branch")

    row.get_by_role("button", name="Review").click()
    diff = p.get_by_role("region", name="Change set diff")
    expect(diff).to_contain_text("1 modified")
    expect(diff).to_contain_text("title")

    row.get_by_role("button", name="Merge").click()
    expect(page.locator(".toast-success").last).to_contain_text("Merged")
    assert page.server.git("branch", "--show-current") == "main"
    assert page.server.get(f"/requirements/{ids['story']['uid']}")["title"] == "Story, edited in a change set"


# --- inbox ---------------------------------------------------------------------------------

def test_inbox_preferences_persist(page):
    open_app(page, product=None)
    open_menu_item(page, "✉ Inbox")
    p = panel(page, "Inbox")
    box = p.get_by_label("status changed")
    expect(box).to_be_checked()
    box.click()  # the box follows the saved preference, so it flips once the server has answered
    expect(box).not_to_be_checked()
    assert "status_changed" not in page.server.get("/notifications/preferences/user")["events"]
    p.get_by_label("Mute all").click()
    expect(p.get_by_label("Mute all")).to_be_checked()
    assert page.server.get("/notifications/preferences/user")["muted"] is True


def test_a_mention_reaches_the_inbox(page):
    ids = seed_tree(page.server)
    page.server.post(f"/requirements/{ids['epic']['uid']}/comments", {"author": "bob", "text": "Over to you @user please"})
    open_app(page)
    open_menu_item(page, "✉ Inbox")
    p = panel(page, "Inbox")
    note = p.locator(".ins-row", has_text="bob")
    expect(note.first).to_be_visible()
    note.first.click()
    expect(field(page, "Title")).to_have_value("Epic one")


# --- query and saved views -----------------------------------------------------------------

def test_query_runs_saves_and_reapplies_a_view(page):
    seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "⌕ Query & saved views")
    p = panel(page, "Query and saved views")
    p.get_by_label("Query").fill("type:story")
    p.get_by_role("button", name="Run").click()
    expect(p.get_by_text("1 match(es)")).to_be_visible()
    page.once("dialog", lambda d: d.accept("My stories"))
    p.get_by_role("button", name="Save view").click()
    expect(p.get_by_role("button", name="My stories", exact=True)).to_be_visible()

    page.reload()
    page.locator("select.header-select").first.select_option("p1")
    open_menu_item(page, "⌕ Query & saved views")
    p = panel(page, "Query and saved views")
    p.get_by_role("button", name="My stories", exact=True).click()
    expect(p.get_by_text("1 match(es)")).to_be_visible()
    p.get_by_label("Delete My stories").click()
    expect(p.get_by_role("button", name="My stories", exact=True)).to_have_count(0)


@pytest.mark.expect_http(422)
def test_a_bad_query_shows_the_error(page):
    open_app(page, product=None)
    open_menu_item(page, "⌕ Query & saved views")
    p = panel(page, "Query and saved views")
    p.get_by_label("Query").fill("status:")
    p.get_by_role("button", name="Run").click()
    expect(p.get_by_role("alert")).to_be_visible()


def test_clicking_a_query_result_opens_the_item(page):
    seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "⌕ Query & saved views")
    p = panel(page, "Query and saved views")
    p.get_by_label("Query").fill("Epic")
    p.get_by_role("button", name="Run").click()
    p.locator(".ins-clickable", has_text="EP-001").click()
    expect(field(page, "Title")).to_have_value("Epic one")


# --- baselines -----------------------------------------------------------------------------

def test_baseline_create_and_field_level_diff(page):
    ids = seed_tree(page.server)
    commit_all(page.server)
    open_app(page)
    open_menu_item(page, "◎ Baselines")
    p = panel(page, "Baselines")
    p.get_by_role("button", name="+ Create baseline").click()
    page.get_by_placeholder("Name (e.g. v1.0-rc1)").fill("rel-1")
    page.get_by_role("button", name="Create", exact=True).click()
    expect(p.get_by_text("rel-1").first).to_be_visible()
    assert "baseline/rel-1" in page.server.git("tag", "--list")

    story = page.server.get(f"/requirements/{ids['story']['uid']}")
    page.server.put(f"/requirements/{ids['story']['uid']}", {**story, "title": "Story, changed after the baseline"})
    commit_all(page.server, "after")
    p.get_by_role("button", name="Diff vs now").click()
    fields = p.get_by_role("region", name="Field-level changes")
    expect(fields).to_contain_text("title")
    expect(fields).to_contain_text("Story, changed after the baseline")
