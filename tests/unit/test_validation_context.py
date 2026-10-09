"""ARC-05: validation rules run on a ``ValidationContext`` built by hand: no store, no files, no git."""

from pathlib import Path

from reqtool.models import CoreEnums, HierarchyConfig, RepoConfig
from reqtool.validation import validate_context, validate_one
from reqtool.validation_context import ValidationContext


def req(uid, **kw):
    base = {"schema_version": "1.0.0", "type": "requirement", "uid": uid, "id": uid.upper(), "title": uid,
            "version": "1.0.0", "status": "draft", "priority": "medium", "req_type": "functional",
            "content": {"description": "The system shall work."}, "created": "x", "last_modified": "x",
            "relationships": [], "links": []}
    base.update(kw)
    return base


def context(*reqs, **kw):
    table = {r["uid"]: r for r in reqs}
    kw.setdefault("merged_enums", CoreEnums().model_dump())
    return ValidationContext(root=Path("/nonexistent"), requirements=table, all_uids=set(table), **kw)


def codes(result, kind="errors"):
    return [i["code"] for i in result[kind]]


def test_rules_run_without_a_store():
    result = validate_context(context(req("a")))
    assert "duplicate_id" not in codes(result)


def test_a_duplicate_id_is_found_from_the_context_alone():
    a, b = req("a"), req("b")
    b["id"] = a["id"]
    assert codes(validate_context(context(a, b))).count("duplicate_id") == 2


def test_a_parent_cycle_is_found_from_the_context_alone():
    a, b = req("a", parentId="b"), req("b", parentId="a")
    assert "parent_cycle" in codes(validate_context(context(a, b)))


def test_hierarchy_rules_use_the_context_hierarchy():
    hierarchy = HierarchyConfig.model_validate({"enforce": "error", "hierarchy": {"theme": {"allowed_children": ["initiative"]}},
                                                "types": {t: {"label": t} for t in ("theme", "epic", "initiative")}})
    theme, epic = req("t", req_type="theme"), req("e", req_type="epic", parentId="t")
    result = validate_context(context(theme, epic, hierarchy=hierarchy))
    assert "hierarchy_violation" in codes(result)


def test_policy_comes_from_the_context():
    cfg = RepoConfig().validation
    cfg.require_owner = False
    quiet = validate_context(context(req("a"), cfg=cfg))
    cfg.require_owner = True
    loud = validate_context(context(req("a"), cfg=cfg))
    assert len(loud["warnings"]) + len(loud["errors"]) > len(quiet["warnings"]) + len(quiet["errors"])


def test_custom_field_rules_are_injected():
    ctx = context(req("a"), custom_field_errors=lambda r: [{"message": "bad", "field": "custom_fields.x"}])
    assert "invalid_custom_field" in codes(validate_context(ctx))


def test_validate_one_finds_an_item_or_reports_it_missing():
    ctx = context(req("a"))
    assert codes(validate_one(ctx, "a")) == []
    assert codes(validate_one(ctx, "zzz")) == ["not_found"]


def test_only_the_two_entry_points_know_about_the_store():
    """Every rule takes a context. ``validate_all`` and ``validate_single`` are the only functions that accept a Store."""
    import ast
    import inspect
    import reqtool.validation as module
    tree = ast.parse(inspect.getsource(module))
    takes_store = sorted(
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and any(arg.annotation is not None and "Store" in ast.unparse(arg.annotation) for arg in node.args.args))
    assert takes_store == ["validate_all", "validate_single"]
    assert "locals()" not in inspect.getsource(module)
