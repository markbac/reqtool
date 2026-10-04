"""QA-03: nothing outside store.py reaches into Store internals. New uses of its private members fail here."""
import re
from pathlib import Path

ROUTERS = Path(__file__).parent.parent / "src" / "reqtool"  # the whole package, store.py aside

# Private Store members routers already use; shrink this set (never grow it) as ARC work lands.
ALLOWED: set[str] = set()


def test_routers_do_not_reach_into_store_internals():
    found = {}
    for path in ROUTERS.rglob("*.py"):
        if path.name == "store.py" and path.parent == ROUTERS:
            continue
        for name in re.findall(r"\bstore\.(_[A-Za-z]\w*)", path.read_text(encoding="utf-8")):
            found.setdefault(name, set()).add(path.name)
    new = {n: sorted(f) for n, f in found.items() if n not in ALLOWED}
    assert not new, f"Routers use private Store members {new}; add a public method instead"
