"""ARC-02: nothing outside the store reaches into its collections.

``store.requirements`` and the others are an implementation detail. Code elsewhere reads through
``requirement_map()``, ``live_requirements()`` and the like (``store_parts/access.py``), so the way artefacts are
kept can change in one place.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "reqtool"
COLLECTIONS = {"requirements", "principles", "decisions", "modules", "products", "module_requirements", "tbds"}
INSIDE = {SRC / "store.py"}


def _is_store(node: ast.AST) -> bool:
    """True for ``store``, ``_store``, ``self.store``, ``app.state.store`` and ``_store(repo)``."""
    if isinstance(node, ast.Call):
        return _is_store(node.func)
    if isinstance(node, ast.Name):
        return node.id.lstrip("_") == "store"
    if isinstance(node, ast.Attribute):
        return node.attr.lstrip("_") == "store"
    return False


def test_no_module_outside_the_store_reads_its_collections_directly():
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        if path in INSIDE or SRC / "store_parts" in path.parents:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in COLLECTIONS and _is_store(node.value):
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno} .{node.attr}")
    assert not offenders, "use the Store accessors (store_parts/access.py) instead of:\n" + "\n".join(offenders)


def test_the_views_are_read_only(repo_root):
    from reqtool.store import Store
    store = Store(repo_root)
    store.load()
    for view in (store.requirement_map(), store.principle_map(), store.decision_map(),
                 store.module_map(), store.product_map()):
        try:
            view["x"] = {}  # type: ignore[index]
        except TypeError:
            continue
        raise AssertionError("a view accepted a write")


def test_a_reload_never_shows_a_reader_empty_modules_or_products(repo_root):
    """ARC-02: load() swaps every collection in one step, so a concurrent reader sees old or new, never nothing."""
    import threading
    from reqtool.store import Store
    store = Store(repo_root)
    store.load()
    store.create_requirement({"title": "r"})
    (repo_root / "products" / "p1").mkdir(parents=True)
    (repo_root / "products" / "p1" / "_product.yaml").write_text("id: p1\ntitle: P1\n", encoding="utf-8")
    (repo_root / "modules" / "m1").mkdir(parents=True)
    (repo_root / "modules" / "m1" / "_module.yaml").write_text("id: m1\ntitle: M1\nversion: 1.0.0\n", encoding="utf-8")
    store.load()
    stop = threading.Event()

    def reload_forever():
        while not stop.is_set():
            store.load()

    worker = threading.Thread(target=reload_forever, daemon=True)
    worker.start()
    try:
        for _ in range(3000):
            assert len(store.product_map()) == 1 and len(store.module_map()) == 1
            assert len(store.requirement_map()) == 1
    finally:
        stop.set()
        worker.join(timeout=10)
