"""QA-03: routers go through Store's public methods. New uses of its private members fail here."""
import re
from pathlib import Path

ROUTERS = Path(__file__).parent.parent / "src" / "reqtool" / "routers"

# Private Store members routers already use; shrink this set (never grow it) as ARC work lands.
ALLOWED = {"_get_artefact", "_lock"}


def test_routers_do_not_reach_into_store_internals():
    found = {}
    for path in ROUTERS.glob("*.py"):
        for name in re.findall(r"\bstore\.(_[A-Za-z]\w*)", path.read_text(encoding="utf-8")):
            found.setdefault(name, set()).add(path.name)
    new = {n: sorted(f) for n, f in found.items() if n not in ALLOWED}
    assert not new, f"Routers use private Store members {new}; add a public method instead"
