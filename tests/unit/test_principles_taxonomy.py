"""Principle areas, categories and the default packs (PRN-01, PRN-02)."""
import re

import pytest

from reqtool import principles as pr

LEGACY_IDS = {
    "P-BUS-CUSTOMER-FIRST", "P-BUS-EXPLICIT-TRADEOFFS", "P-BUS-DEFER-COMMITMENT",
    "P-ARCH-ADR", "P-ARCH-SINGLE-RESPONSIBILITY", "P-ARCH-EXPLICIT-INTERFACES", "P-ARCH-FAIL-SAFE",
    "P-ARCH-DEPENDENCY-DIRECTION", "P-SEC-UNIQUE-CREDS", "P-SEC-PKI", "P-SEC-NO-SECRETS-IN-CODE",
    "P-SEC-OTA", "P-SEC-TLS", "P-FW-WATCHDOG", "P-FW-SEMVER", "P-FW-FAIL-KNOWN-STATE",
    "P-FW-NO-BUSY-WAIT", "P-FW-PERSISTENT-CONFIG", "P-COMMS-MQTT", "P-COMMS-JSON", "P-COMMS-NTP",
    "P-COMMS-REST-LOCAL", "P-DATA-IMMUTABLE-LOGS", "P-DATA-SCHEMA-VERSIONED", "P-DATA-MINIMAL-COLLECTION",
    "P-PROC-CI", "P-PROC-TEST-BEFORE-MERGE", "P-PROC-DEFINITION-OF-DONE", "P-PROC-BLAMELESS-POSTMORTEM",
    "P-SAF-HAZARD-ANALYSIS", "P-SAF-INDEPENDENCE",
}


def all_principles():
    for area in pr.pack_areas():
        for p in pr.load_pack(area)["principles"]:
            yield area, p


class TestPacks:
    def test_there_is_a_pack_for_every_area_in_the_order(self):
        assert pr.pack_areas() == list(pr.AREA_ORDER)

    def test_ids_are_unique_across_packs(self):
        ids = [p["id"] for _a, p in all_principles()]
        assert len(ids) == len(set(ids))

    def test_every_principle_has_the_text_that_makes_it_normative(self):
        for area, p in all_principles():
            assert p.get("title"), p["id"]
            assert p.get("description", "").strip(), p["id"]
            assert p.get("rationale", "").strip(), f"{p['id']} has no rationale"

    def test_every_category_is_declared_and_every_pack_has_general(self):
        for area in pr.pack_areas():
            pack = pr.load_pack(area)
            declared = {c["id"] for c in pack["categories"]}
            assert pr.GENERAL in declared, area
            for p in pack["principles"]:
                assert p["category"] in declared, (area, p["id"], p["category"])

    def test_new_ids_follow_area_category_slug(self):
        for area, p in all_principles():
            if p["id"] in LEGACY_IDS:
                continue
            pack = pr.load_pack(area)
            cats = {c["id"]: c["code"] for c in pack["categories"]}
            assert re.fullmatch(rf"P-{pack['code']}-{cats[p['category']]}-[A-Z0-9-]+", p["id"]), p["id"]

    def test_every_original_principle_is_kept_with_its_id(self):
        ids = {p["id"] for _a, p in all_principles()}
        assert LEGACY_IDS <= ids

    def test_architecture_security_exists_as_in_the_brief(self):
        arch = pr.pack_summary("architecture")
        sec = next(c for c in arch["categories"] if c["id"] == "security")
        assert sec["count"] >= 3

    def test_each_area_has_enough_to_be_useful(self):
        for area in pr.pack_areas():
            assert pr.pack_summary(area)["count"] >= 10, area

    def test_pack_principles_are_store_ready(self):
        first = pr.pack_principles("security")[0]
        assert first["area"] == "security" and first["category"] and first["content"]["description"]

    def test_unknown_pack_is_a_clear_error(self):
        with pytest.raises(KeyError, match="Available"):
            pr.load_pack("nope")

    def test_flavours_only_name_real_packs(self):
        for flavour, areas in pr.FLAVOUR_PACKS.items():
            assert set(areas) <= set(pr.pack_areas()), flavour


class TestPlacement:
    def test_old_domain_maps_to_area_and_category(self):
        assert pr.legacy_placement("security") == ("architecture", "security")
        assert pr.legacy_placement("firmware") == ("hardware_firmware", "general")
        assert pr.legacy_placement("COMMS") == ("architecture", "integration")
        assert pr.legacy_placement("something-custom") == (None, None)
        assert pr.legacy_placement(None) == (None, None)

    def test_stored_area_wins_then_pack_id_then_domain(self):
        assert pr.placement({"id": "P-SEC-TLS", "area": "business", "category": "risk"}) == ("business", "risk")
        assert pr.placement({"id": "P-SEC-TLS", "domain": "security"}) == ("security", "cryptography")
        assert pr.placement({"id": "P-MINE", "domain": "security"}) == ("architecture", "security")
        assert pr.placement({"id": "P-MINE"}) == (None, None)

    def test_area_without_category_is_general(self):
        assert pr.placement({"area": "product"}) == ("product", "general")

    def test_normalise_fills_area_from_domain_only(self):
        assert pr.normalise_fields({"domain": "data"})["area"] == "data_privacy"
        kept = pr.normalise_fields({"area": "product", "category": "scope", "domain": "data"})
        assert (kept["area"], kept["category"]) == ("product", "scope")
        assert pr.normalise_fields({"area": "product"})["category"] == "general"

    def test_check_placement(self):
        vocab = pr.default_vocabulary()
        assert pr.check_placement(None, None, vocab) is None
        assert pr.check_placement("architecture", "security", vocab) is None
        assert "Area 'x'" in pr.check_placement("x", None, vocab)
        assert "Category 'y'" in pr.check_placement("architecture", "y", vocab)

    def test_make_id_is_unique_and_readable(self):
        vocab = pr.default_vocabulary()
        first = pr.make_id("architecture", "security", "Use mTLS everywhere!", vocab, [])
        assert first == "P-ARCH-SEC-USE-MTLS-EVERYWHERE"
        assert pr.make_id("architecture", "security", "Use mTLS everywhere!", vocab, [first]) == first + "-2"


class TestVocabulary:
    def test_repository_without_one_uses_the_defaults(self):
        assert set(pr.effective_vocabulary({})) == set(pr.AREA_ORDER)

    def test_a_repository_vocabulary_replaces_the_defaults(self):
        v = pr.effective_vocabulary({"team": {"label": "Team rules", "categories": {"review": {"label": "Review"}}}})
        assert list(v) == ["team"] and v["team"]["categories"]["review"]["code"] == "REVIE"

    @pytest.mark.parametrize("bad", [{"Bad Area": {}}, {"ok": {"categories": {"Bad Cat": {}}}}])
    def test_malformed_ids_are_refused(self, bad):
        with pytest.raises(ValueError):
            pr.clean_vocabulary(bad)

    def test_merging_a_pack_keeps_what_is_there(self):
        mine = {"security": {"label": "Our security", "code": "S", "categories": {"identity": {"label": "Who", "code": "W"}}}}
        merged = pr.merge_pack_into(mine, "security")
        assert merged["security"]["label"] == "Our security"
        assert merged["security"]["categories"]["identity"]["label"] == "Who"
        assert "cryptography" in merged["security"]["categories"]
        assert "label" in pr.merge_pack_into({}, "product")["product"]


class TestAreaTree:
    def test_counts_by_area_and_category_with_unknown_and_unplaced(self):
        vocab = pr.default_vocabulary(["architecture", "security"])
        items = [
            {"id": "P-SEC-TLS"},                                   # from the pack: security > cryptography
            {"id": "a", "area": "architecture", "category": "security"},
            {"id": "b", "area": "architecture", "category": "made-up"},
            {"id": "c", "area": "elsewhere", "category": "general"},
            {"id": "d"},
        ]
        tree = pr.area_tree(items, vocab)
        by = {a["id"]: a for a in tree["areas"]}
        assert [a["id"] for a in tree["areas"]] == ["architecture", "security", "elsewhere"]
        assert by["architecture"]["count"] == 2
        assert {c["id"]: c["count"] for c in by["architecture"]["categories"] if c["count"]} == {"security": 1, "made-up": 1}
        assert by["architecture"]["categories"][-1]["known"] is False
        assert by["security"]["count"] == 1 and by["elsewhere"]["known"] is False
        assert tree["unplaced"] == 1 and tree["total"] == 5

    def test_with_placement_marks_derived(self):
        out = pr.with_placement({"id": "P-SEC-TLS"})
        assert out["area"] == "security" and out["placement_derived"] is True
        assert "placement_derived" not in pr.with_placement({"id": "x", "area": "product"})
