"""The tool panels under the header menu: bulk update, traceability, vocabularies, custom fields, webhooks,
workflow, templates, CSV import, iterations, diagrams, automation rules, duplicates and the repository panel."""

from playwright.sync_api import expect

from .helpers import open_app, open_menu_item, panel, seed_tree, wait_until


def test_bulk_update_changes_the_selected_items_only(page):
    ids = seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "≡ Bulk update")
    p = panel(page, "Bulk Update")
    p.get_by_text("EP-001").click()
    p.get_by_text("US-001").click()
    expect(p.locator(".side-panel-title, button.btn-primary").filter(has_text="Apply to 2")).to_be_visible()
    p.locator("select").nth(1).select_option("high")
    p.get_by_role("button", name="Apply to 2 requirement(s)").click()
    expect(page.locator(".toast", has_text="Updated 2 requirement(s)")).to_be_visible()
    got = {r["id"]: r["priority"] for r in page.server.get("/requirements")}
    assert got["EP-001"] == got["US-001"] == "high"
    assert got["TH-001"] != "high"


def test_bulk_update_without_a_change_is_refused_politely(page):
    seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "≡ Bulk update")
    p = panel(page, "Bulk Update")
    p.get_by_text("US-001").click()
    p.get_by_role("button", name="Apply to 1 requirement(s)").click()
    expect(page.locator(".toast", has_text="No fields to update")).to_be_visible()


def test_traceability_matrix_shows_allocations(page):
    ids = seed_tree(page.server)
    story = page.server.get(f"/requirements/{ids['story']['uid']}")
    page.server.put(f"/requirements/{ids['story']['uid']}", {**story, "allocated_to": ["platform"]})
    open_app(page)
    open_menu_item(page, "⊗ Traceability")
    table = page.locator(".trace-table")
    expect(table.locator("th", has_text="platform")).to_be_visible()
    row = table.locator("tr", has_text="US-001")
    expect(row.locator(".trace-check")).to_have_count(1)
    expect(table.locator("tr", has_text="TH-001").locator(".trace-check")).to_have_count(0)


def test_coverage_panel_counts_quality_gaps(page):
    seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "⊞ Coverage")
    p = panel(page, "Coverage")
    expect(p).to_contain_text("4 requirements")
    expect(p).to_contain_text("No acceptance criteria")


def test_vocabularies_add_rename_remove_and_save(page):
    open_app(page)
    open_menu_item(page, "⊙ Vocabularies")
    p = panel(page, "Vocabularies")
    p.locator(".vocab-nav-item", has_text="Teams").click()
    labels = p.locator(".vocab-item-label")
    start = labels.all_inner_texts()
    add = p.get_by_placeholder("Add new entry...")
    add.fill("guild-a")
    p.get_by_role("button", name="+ Add").click()
    add.fill("guild-b")
    add.press("Enter")
    expect(labels).to_have_text(start + ["guild-a", "guild-b"])
    p.locator(".vocab-item", has_text="guild-b").get_by_role("button", name="✕").click()
    p.locator(".vocab-item", has_text="guild-a").get_by_role("button", name="✎").click()
    p.locator(".vocab-item-input").fill("guild-renamed")
    p.locator(".vocab-item-input").press("Enter")
    expect(labels).to_have_text(start + ["guild-renamed"])
    p.get_by_role("button", name="Save", exact=True).click()
    expect(page.locator(".toast", has_text="Vocabularies saved")).to_be_visible()
    assert page.server.get("/enums/repo")["team"] == start + ["guild-renamed"]
    add.fill("guild-renamed")  # a duplicate is refused
    p.get_by_role("button", name="+ Add").click()
    expect(page.locator(".toast", has_text="already exists")).to_be_visible()


def test_custom_field_schema_saves_and_appears_in_the_editor(page):
    ids = seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "⊚ Custom fields")
    p = panel(page, "Custom")
    p.get_by_role("button", name="+ Add field").click()
    p.get_by_placeholder("key (snake_case)").fill("customer_ref")
    p.get_by_placeholder("Display label").fill("Customer reference")
    p.get_by_role("button", name="Save").click()
    expect(page.locator(".toast", has_text="Custom field schema saved")).to_be_visible()
    assert [f["key"] for f in page.server.get("/custom-fields")] == ["customer_ref"]
    page.reload()  # the schema is read when the app loads
    page.locator("select.header-select").first.select_option("p1")
    page.locator(".tree-node", has_text="TH-001").click()
    page.get_by_role("button", name="Relationships & Links").click()
    expect(page.locator(".attr-key", has_text="Customer reference")).to_be_visible()


def test_custom_field_keys_must_be_unique(page):
    open_app(page)
    open_menu_item(page, "⊚ Custom fields")
    p = panel(page, "Custom")
    for _ in range(2):
        p.get_by_role("button", name="+ Add field").click()
    keys = p.get_by_placeholder("key (snake_case)")
    keys.nth(0).fill("same")
    keys.nth(1).fill("same")
    p.get_by_role("button", name="Save").click()
    expect(page.locator(".toast", has_text="must be unique")).to_be_visible()
    assert page.server.get("/custom-fields") == []


def test_webhook_add_list_and_delete(page):
    open_app(page)
    open_menu_item(page, "⇌ Webhooks")
    p = panel(page, "Webhooks")
    p.get_by_role("button", name="+ Add webhook").click()
    p.get_by_placeholder("https://hooks.example.com/reqtool").fill("https://hooks.example.com/one")
    p.get_by_role("button", name="Add", exact=True).click()
    expect(page.locator(".toast", has_text="Webhook added")).to_be_visible()
    expect(p.locator(".webhook-url")).to_have_text(["https://hooks.example.com/one"])
    assert [w["url"] for w in page.server.get("/webhooks")] == ["https://hooks.example.com/one"]
    page.once("dialog", lambda d: d.accept())
    p.locator(".webhook-item").get_by_role("button", name="✕").click()
    expect(p.locator(".webhook-item")).to_have_count(0)
    assert page.server.get("/webhooks") == []


def test_workflow_panel_shows_states_and_saves(page):
    open_app(page)
    open_menu_item(page, "⬡ Fallback workflow")
    expect(page.get_by_text("Workflow").first).to_be_visible()
    page.get_by_role("button", name="Save").first.click()
    expect(page.locator(".toast", has_text="Workflow saved")).to_be_visible()


def test_template_use_then_new_creates_from_it(page):
    templates = page.server.get("/templates")
    assert templates, "the agile flavour ships templates"
    open_app(page)
    open_menu_item(page, "▤ Templates")
    p = panel(page, "Templates")
    first = p.locator(".template-item").first
    label = first.locator(".template-label").inner_text()
    first.get_by_role("button", name="Use").click()
    expect(page.locator(".toast", has_text=f"Template '{label}' ready")).to_be_visible()
    expect(page.locator(".side-panel")).to_have_count(0)  # the panel closes itself
    expect(page.locator(".tree-template-active")).to_contain_text(label)
    page.get_by_role("button", name="+ New", exact=True).first.click()
    wait_until(lambda: page.server.get("/requirements"), what="the item made from the template")
    expect(page.locator(".tree-template-active")).to_have_count(0)


def test_csv_import_creates_requirements(page, tmp_path):
    csv = tmp_path / "in.csv"
    csv.write_text("title,status,priority\nFirst imported,draft,high\nSecond imported,draft,low\n", encoding="utf-8")
    open_app(page)
    open_menu_item(page, "↑ Import CSV")
    p = panel(page, "Import from CSV")
    p.locator("input[type=file]").set_input_files(str(csv))
    expect(p.locator(".import-preview-text")).to_contain_text("First imported")
    p.get_by_role("button", name="Import").click()
    expect(page.locator(".tree-node", has_text="Second imported")).to_be_visible()
    assert sorted(r["title"] for r in page.server.get("/requirements")) == ["First imported", "Second imported"]


def test_iteration_can_be_created_and_deleted(page):
    open_app(page)
    open_menu_item(page, "⏱ Iterations & Gates")
    p = panel(page, "Iteration")
    p.get_by_role("button", name="+ New").click()
    p.locator("input[type=text]").nth(0).fill("sprint-e2e")
    p.locator("input[type=text]").nth(1).fill("E2E sprint")
    p.get_by_role("button", name="Save").click()
    expect(page.locator(".toast", has_text="Saved iteration 'sprint-e2e'")).to_be_visible()
    assert "sprint-e2e" in [i["id"] for i in page.server.get("/iterations")]
    p.locator("div", has_text="E2E sprint").last.click()  # the list reselects the first item after a save
    page.once("dialog", lambda d: d.accept())
    p.get_by_role("button", name="Delete").click()
    wait_until(lambda: "sprint-e2e" not in [i["id"] for i in page.server.get("/iterations")], what="the deletion")


def test_diagram_canvas_renders_mermaid_and_switches_engine(page):
    seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "🎨 Diagram Canvas")
    p = panel(page, "Diagram Canvas")
    expect(p).to_contain_text("graph TD")
    p.get_by_text("PlantUML (Backend plantuml.jar)").click()
    expect(p).to_contain_text("Diagram")


def test_automation_rules_open_and_save(page):
    open_app(page)
    open_menu_item(page, "🤖 Automation Rules")
    p = panel(page, "Automation Rules")
    expect(p).to_contain_text("Trigger event")
    p.get_by_role("button", name="Save Rules").click()
    expect(page.locator(".toast").last).to_be_visible()


def test_duplicate_detector_lists_pairs_and_rescans(page):
    seed_tree(page.server)  # every seeded item shares one description, so they pair up
    open_app(page)
    open_menu_item(page, "✨ Duplicate Detector")
    p = panel(page, "Duplicate")
    expect(p).to_contain_text("Pair #1")
    p.get_by_role("button", name="Re-scan").click()
    expect(p).to_contain_text("Similarity")


def test_repository_panel_shows_the_active_repo(page):
    seed_tree(page.server)
    open_app(page)
    open_menu_item(page, "📦 Repository")
    p = panel(page, "Repository")
    expect(p).to_contain_text("Active: E2E (e2e)")
    expect(p).to_contain_text("4 requirements")
