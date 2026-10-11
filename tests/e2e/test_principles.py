"""Principles by area and category in the browser (PRN-03): browse, filter, move, and add default packs."""

import pytest
from playwright.sync_api import expect

from .conftest import start_server
from .helpers import open_app, wait_until


@pytest.fixture
def server(tmp_path):
    s = start_server(tmp_path / "repo", "agile", principles=None)   # the agile flavour's default packs
    yield s
    s.stop()


def open_principles(page):
    open_app(page)
    page.locator(".sidebar-tab", has_text="Principles").click()
    expect(page.locator(".principle-area-header").first).to_be_visible()


def area(page, area_id):
    return page.locator(f'.principle-group[data-area="{area_id}"]')


def category(page, area_id, category_id):
    return area(page, area_id).locator(f'.principle-category[data-category="{category_id}"]')


def test_areas_open_to_categories_then_principles(page):
    open_principles(page)
    labels = [t.lower() for t in page.locator(".principle-area-header .principle-group-label").all_inner_texts()]
    assert labels[:3] == ["business", "product", "architecture"]
    assert "hardware and firmware" not in labels   # not in the agile set
    assert page.locator(".principle-row").count() == 0
    area(page, "architecture").locator(".principle-area-header").click()
    category(page, "architecture", "security").locator(".principle-category-toggle").click()
    rows = category(page, "architecture", "security").locator(".principle-row")
    expect(rows.first).to_be_visible()
    assert rows.count() >= 5
    assert page.server.get("/principles/areas")["total"] == len(page.server.get("/principles"))


def test_selecting_a_principle_shows_its_area_and_category(page):
    open_principles(page)
    area(page, "architecture").locator(".principle-area-header").click()
    category(page, "architecture", "security").locator(".principle-category-toggle").click()
    category(page, "architecture", "security").locator(".principle-row").first.click()
    expect(page.get_by_label("Area")).to_have_value("architecture")
    expect(page.get_by_label("Category")).to_have_value("security")


def test_changing_the_category_in_the_editor_moves_it_in_the_tree(page):
    open_principles(page)
    area(page, "architecture").locator(".principle-area-header").click()
    category(page, "architecture", "security").locator(".principle-category-toggle").click()
    row = category(page, "architecture", "security").locator(".principle-row").first
    pid = row.locator(".list-item-id").inner_text()
    row.click()
    page.get_by_label("Category").select_option("resilience")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.locator(".toast", has_text="Saved")).to_be_visible()
    wait_until(lambda: next(p for p in page.server.get("/principles") if p["id"] == pid)["category"] == "resilience",
               what="the principle in its new category")
    expect(category(page, "architecture", "resilience").locator(".principle-row", has_text=pid)).to_be_visible()
    expect(category(page, "architecture", "security").locator(".principle-row", has_text=pid)).to_have_count(0)


def test_dragging_a_principle_onto_a_category_moves_it(page):
    open_principles(page)
    area(page, "architecture").locator(".principle-area-header").click()
    category(page, "architecture", "security").locator(".principle-category-toggle").click()
    category(page, "architecture", "structure").locator(".principle-category-toggle").click()
    row = category(page, "architecture", "security").locator(".principle-row").first
    pid = row.locator(".list-item-id").inner_text()
    row.drag_to(category(page, "architecture", "structure").locator(".principle-category-header"))
    expect(page.locator(".toast", has_text=f"Moved {pid}")).to_be_visible()
    expect(category(page, "architecture", "structure").locator(".principle-row", has_text=pid)).to_be_visible()


def test_search_and_status_filter_narrow_the_tree(page):
    open_principles(page)
    page.get_by_placeholder("Search principles...").fill("least privilege")
    rows = page.locator(".principle-row")
    expect(rows).to_have_count(1)
    expect(area(page, "architecture").locator(".principle-row")).to_have_count(1)
    page.get_by_placeholder("Search principles...").fill("zzz-nothing")
    expect(page.get_by_text("No principles match.")).to_be_visible()


def test_new_principle_inside_a_category(page):
    open_principles(page)
    area(page, "product").locator(".principle-area-header").click()
    page.get_by_label("New principle in Usability and accessibility").click()
    wait_until(lambda: any(p["title"] == "New principle" for p in page.server.get("/principles")), what="the new principle")
    made = next(p for p in page.server.get("/principles") if p["title"] == "New principle")
    assert (made["area"], made["category"]) == ("product", "usability")
    expect(page.get_by_label("Category")).to_have_value("usability")


def test_an_administrator_adds_a_default_pack(page):
    open_principles(page)
    before = len(page.server.get("/principles"))
    expect(area(page, "hardware_firmware")).to_have_count(0)
    page.get_by_role("button", name="+ Defaults").click()
    dialog = page.get_by_role("dialog", name="Add default principles")
    expect(dialog.get_by_label("Security")).to_be_disabled()          # already there
    dialog.get_by_label("Hardware and firmware").check()
    dialog.get_by_role("button", name="Add 1 pack").click()
    expect(page.locator(".toast", has_text="Added")).to_be_visible()
    expect(area(page, "hardware_firmware")).to_be_visible()
    assert len(page.server.get("/principles")) > before
    assert "hardware_firmware" in page.server.get("/principles/vocabulary")["vocabulary"]


def test_an_administrator_adds_a_category(page):
    open_principles(page)
    area(page, "business").locator(".principle-area-header").click()
    category(page, "business", "value").locator(".principle-category-toggle").click()
    category(page, "business", "value").locator(".principle-row").first.click()
    page.get_by_role("button", name="+ New category").click()
    page.get_by_label("New category name").fill("Brand")
    page.get_by_role("button", name="Add", exact=True).click()
    expect(page.locator("#principle-category")).to_have_value("brand")
    assert "brand" in page.server.get("/principles/vocabulary")["vocabulary"]["business"]["categories"]
