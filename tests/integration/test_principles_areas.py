"""Principles by area and category: API, packs, init, migration, validation and export (PRN-01, PRN-02)."""
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from reqtool.api import create_app
from reqtool.cli import cli
from reqtool.fileio import compute_principle_hash, load_yaml, save_yaml
from reqtool.store import Store


def body(**kw):
    return {"title": "A principle", "content": {"description": "The system shall X.", "rationale": "Because."}, **kw}


class TestApi:
    def test_create_with_area_and_category_makes_a_readable_id(self, client):
        p = client.post("/principles", json=body(title="Use mTLS", area="architecture", category="security")).json()
        assert p["id"] == "P-ARCH-SEC-USE-MTLS"
        assert (p["area"], p["category"]) == ("architecture", "security")

    def test_old_domain_alone_still_works_and_is_placed(self, client):
        p = client.post("/principles", json=body(domain="security")).json()
        assert (p["area"], p["category"], p["domain"]) == ("architecture", "security", "security")

    def test_area_without_category_goes_to_general(self, client):
        assert client.post("/principles", json=body(area="product")).json()["category"] == "general"

    def test_list_filters_by_area_category_status_and_text(self, client):
        client.post("/principles", json=body(title="Alpha", area="architecture", category="security"))
        client.post("/principles", json=body(title="Beta", area="architecture", category="structure"))
        client.post("/principles", json=body(title="Gamma", area="product", category="scope"))
        titles = lambda **q: sorted(p["title"] for p in client.get("/principles", params=q).json())
        assert titles() == ["Alpha", "Beta", "Gamma"]
        assert titles(area="architecture") == ["Alpha", "Beta"]
        assert titles(area="architecture", category="security") == ["Alpha"]
        assert titles(q="gam") == ["Gamma"]
        assert titles(status="draft") == ["Alpha", "Beta", "Gamma"]
        assert titles(area="nowhere") == []

    def test_areas_tree_has_counts_and_the_vocabulary_in_order(self, client):
        client.post("/principles", json=body(area="architecture", category="security"))
        client.post("/principles", json=body())
        tree = client.get("/principles/areas").json()
        assert tree["unplaced"] == 1 and tree["total"] == 2
        arch = next(a for a in tree["areas"] if a["id"] == "architecture")
        assert arch["count"] == 1
        assert next(c for c in arch["categories"] if c["id"] == "security")["count"] == 1
        assert [a["id"] for a in tree["areas"]][:3] == ["business", "product", "architecture"]

    def test_update_moves_between_categories(self, client):
        uid = client.post("/principles", json=body(area="architecture", category="security")).json()["uid"]
        moved = client.put(f"/principles/{uid}", json={"area": "product", "category": "scope"}).json()
        assert (moved["area"], moved["category"]) == ("product", "scope")
        again = client.put(f"/principles/{uid}", json={"area": "security"}).json()
        assert (again["area"], again["category"]) == ("security", "general")

    def test_get_derives_a_missing_placement_for_older_principles(self, repo_root):
        store = Store(repo_root)
        store.load()
        made = store.create_principle({"id": "P-SEC-TLS", "title": "TLS"})
        for key in ("area", "category"):   # as a version before areas wrote it
            made.pop(key, None)
        made["content_hash"] = compute_principle_hash(made)
        store.storage.write(store.principle_path(made["uid"]), made)
        client = TestClient(create_app(repo_root))
        got = client.get(f"/principles/{made['uid']}").json()
        assert got["area"] == "security" and got["category"] == "cryptography" and got["placement_derived"] is True

    def test_packs_listing_counts_what_is_installed(self, client):
        packs = {p["area"]: p for p in client.get("/principles/packs").json()}
        assert set(packs) >= {"architecture", "security", "operations"}
        assert packs["security"]["installed"] == 0 and packs["security"]["available"] == packs["security"]["count"]

    def test_adding_a_pack_is_idempotent(self, client):
        first = client.post("/principles/packs/security").json()
        assert first["added"] > 0 and first["skipped"] == 0
        second = client.post("/principles/packs/security").json()
        assert second == {"area": "security", "added": 0, "skipped": first["added"]}
        listed = client.get("/principles", params={"area": "security"}).json()
        assert len(listed) == first["added"]
        assert next(p for p in client.get("/principles/packs").json() if p["area"] == "security")["available"] == 0

    def test_a_deleted_pack_principle_is_not_resurrected(self, client):
        client.post("/principles/packs/business")
        victim = client.get("/principles", params={"area": "business"}).json()[0]
        client.delete(f"/principles/{victim['uid']}")
        assert client.post("/principles/packs/business").json()["added"] == 0

    def test_unknown_pack_is_a_404(self, client):
        assert client.post("/principles/packs/nope").status_code == 404

    def test_vocabulary_can_be_replaced_and_is_stored_in_enums(self, client, repo_root):
        assert client.get("/principles/vocabulary").json()["custom"] is False
        r = client.put("/principles/vocabulary", json={"vocabulary": {
            "team": {"label": "Team rules", "categories": {"review": {"label": "Review"}}}}})
        assert r.status_code == 200 and r.json()["vocabulary"]["team"]["categories"]["review"]["label"] == "Review"
        assert client.get("/principles/vocabulary").json()["custom"] is True
        assert load_yaml(repo_root / ".reqtool" / "enums.yaml")["principle_areas"]["team"]["label"] == "Team rules"
        assert client.get("/enums/repo").json()["principle_areas"]["team"]

    def test_bad_vocabulary_is_refused(self, client):
        assert client.put("/principles/vocabulary", json={"vocabulary": {"Bad Area": {}}}).status_code == 422

    def test_adding_a_pack_extends_a_custom_vocabulary(self, client):
        client.put("/principles/vocabulary", json={"vocabulary": {"team": {"label": "Team rules"}}})
        client.post("/principles/packs/product")
        vocab = client.get("/principles/vocabulary").json()["vocabulary"]
        assert "team" in vocab and "scope" in vocab["product"]["categories"]


class TestValidation:
    def messages(self, client):
        data = client.get("/validate").json()
        return [w for w in data.get("warnings", []) if w.get("code", "").startswith("unknown_principle")]

    def test_unknown_area_and_category_warn(self, client):
        client.post("/principles", json=body(area="made_up", category="x"))
        client.post("/principles", json=body(area="architecture", category="made-up"))
        codes = sorted(w["code"] for w in self.messages(client))
        assert codes == ["unknown_principle_area", "unknown_principle_category"]

    def test_known_and_unplaced_principles_do_not_warn(self, client):
        client.post("/principles", json=body(area="architecture", category="security"))
        client.post("/principles", json=body())
        assert self.messages(client) == []


class TestInit:
    def run(self, tmp_path, *args):
        return CliRunner().invoke(cli, ["init", *args, "--repo", str(tmp_path), "--id", "x", "--title", "X"])

    def areas(self, tmp_path):
        s = Store(tmp_path)
        s.load()
        return s, {p["area"] for p in s.principle_map().values()}

    def test_defaults_includes_every_area_and_writes_the_vocabulary(self, tmp_path):
        r = self.run(tmp_path, "defaults")
        assert r.exit_code == 0, r.output
        store, areas = self.areas(tmp_path)
        assert len(areas) == 10 and set(store.repo_enums.principle_areas) == areas
        assert "areas and" in r.output and "architecture" in r.output

    def test_agile_and_systems_get_a_sensible_default_set(self, tmp_path):
        agile, systems = tmp_path / "a", tmp_path / "s"
        assert self.run(agile, "agile").exit_code == 0 and self.run(systems, "systems").exit_code == 0
        _s, a_areas = self.areas(agile)
        _s, s_areas = self.areas(systems)
        assert "safety_quality" not in a_areas and "hardware_firmware" not in a_areas and "product" in a_areas
        assert {"safety_quality", "hardware_firmware"} <= s_areas

    def test_choose_packs_none_all_or_a_list(self, tmp_path):
        none, some, every = tmp_path / "n", tmp_path / "l", tmp_path / "e"
        assert self.run(none, "agile", "--principles", "none").exit_code == 0
        assert not Store(none).load() and self.areas(none)[1] == set()
        assert self.run(some, "agile", "--principles", "security, product").exit_code == 0
        assert self.areas(some)[1] == {"security", "product"}
        assert self.run(every, "agile", "--principles", "all").exit_code == 0
        assert len(self.areas(every)[1]) == 10

    def test_an_unknown_pack_stops_before_anything_is_written(self, tmp_path):
        r = self.run(tmp_path, "agile", "--principles", "nope")
        assert r.exit_code != 0 and "Unknown principle pack" in r.output
        assert not (tmp_path / ".reqtool" / "config.yaml").exists()


class TestPrinciplesCommands:
    def setup_repo(self, tmp_path):
        CliRunner().invoke(cli, ["init", "agile", "--repo", str(tmp_path), "--id", "x", "--title", "X", "--principles", "none"])

    def test_packs_lists_and_add_pack_adds_without_duplicating(self, tmp_path):
        self.setup_repo(tmp_path)
        out = CliRunner().invoke(cli, ["principles", "packs", "--repo", str(tmp_path)]).output
        assert "security" in out and "0 of" in out
        first = CliRunner().invoke(cli, ["principles", "add-pack", "security", "product", "--repo", str(tmp_path)])
        assert first.exit_code == 0 and "security: added" in first.output
        again = CliRunner().invoke(cli, ["principles", "add-pack", "security", "--repo", str(tmp_path)])
        assert "added 0" in again.output
        s = Store(tmp_path)
        s.load()
        assert {p["area"] for p in s.principle_map().values()} == {"security", "product"}

    def test_add_pack_all_and_unknown(self, tmp_path):
        self.setup_repo(tmp_path)
        assert CliRunner().invoke(cli, ["principles", "add-pack", "all", "--repo", str(tmp_path)]).exit_code == 0
        bad = CliRunner().invoke(cli, ["principles", "add-pack", "nope", "--repo", str(tmp_path)])
        assert bad.exit_code != 0 and "No principle pack" in bad.output


class TestMigration:
    def old_repo(self, tmp_path):
        """A repository made before areas existed: principles with only a domain, and no vocabulary."""
        CliRunner().invoke(cli, ["init", "agile", "--repo", str(tmp_path), "--id", "x", "--title", "X", "--principles", "none"])
        s = Store(tmp_path)
        s.load()
        made = {
            "default": s.create_principle({"id": "P-SEC-TLS", "title": "TLS", "domain": "security"}),
            "custom": s.create_principle({"id": "P-OURS-1", "title": "Ours", "domain": "process"}),
            "odd": s.create_principle({"id": "P-ODD", "title": "Odd", "domain": "whimsy"}),
        }
        for p in made.values():  # as an older version wrote them
            for key in ("area", "category"):
                p.pop(key, None)
            p["content_hash"] = compute_principle_hash(p)
            s.storage.write(s.principle_path(p["uid"]), p)
        return made

    def test_migrate_places_principles_and_writes_the_vocabulary(self, tmp_path):
        self.old_repo(tmp_path)
        r = CliRunner().invoke(cli, ["migrate", "--repo", str(tmp_path)])
        assert r.exit_code == 0, r.output
        assert "placed in an area and category: 2" in r.output and "P-ODD" in r.output
        s = Store(tmp_path)
        s.load()
        by = {p["id"]: p for p in s.principle_map().values()}
        assert (by["P-SEC-TLS"]["area"], by["P-SEC-TLS"]["category"]) == ("security", "cryptography")
        assert (by["P-OURS-1"]["area"], by["P-OURS-1"]["category"]) == ("delivery", "general")
        assert not by["P-ODD"].get("area")
        assert set(s.repo_enums.principle_areas) == {"security", "delivery"}

    def test_migrate_twice_changes_nothing_more(self, tmp_path):
        self.old_repo(tmp_path)
        CliRunner().invoke(cli, ["migrate", "--repo", str(tmp_path)])
        s = Store(tmp_path)
        s.load()
        before = {p["id"]: (p["version"], p["content_hash"]) for p in s.principle_map().values()}
        r = CliRunner().invoke(cli, ["migrate", "--repo", str(tmp_path)])
        assert "placed in an area and category: 0" in r.output
        s2 = Store(tmp_path)
        s2.load()
        assert {p["id"]: (p["version"], p["content_hash"]) for p in s2.principle_map().values()} == before

    def test_a_placed_principle_validates_cleanly_after_migration(self, tmp_path):
        self.old_repo(tmp_path)
        CliRunner().invoke(cli, ["migrate", "--repo", str(tmp_path)])
        s = Store(tmp_path)
        s.load()
        from reqtool.validation import validate_all
        result = validate_all(s)
        errors = [e for e in (result.get("errors") if isinstance(result, dict) else result.errors) if "hash" in str(e)]
        assert errors == []

    def test_old_principle_files_still_load_unchanged(self, tmp_path):
        made = self.old_repo(tmp_path)
        s = Store(tmp_path)
        s.load()
        assert len(s.principle_map()) == 3
        assert s.get_principle(made["default"]["uid"]).get("area") is None


class TestExport:
    def test_markdown_groups_by_area_then_category(self, client_with_store):
        client, _store = client_with_store
        client.post("/principles", json=body(title="One", area="architecture", category="security"))
        client.post("/principles", json=body(title="Two", area="architecture", category="structure"))
        client.post("/principles", json=body(title="Three", area="business", category="value"))
        from reqtool.exports import export_markdown
        _store.load()   # the test's own store only sees what the app wrote after a reload
        text = export_markdown(_store)["principles.md"]
        order = [text.index(h) for h in ("# Business", "## Value", "# Architecture", "## Structure and layering", "## Security")]
        assert order == sorted(order)
        assert text.index("### P-ARCH-STR") < text.index("### P-ARCH-SEC")
