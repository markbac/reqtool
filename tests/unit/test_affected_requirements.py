"""DAT-07: compute_affected_requirements covers every reference shape."""


def _put(store, uid, **extra):
    store.requirements[uid] = {"uid": uid, "id": uid, **extra}


def test_all_reference_shapes(store):
    store.requirements.clear()
    _put(store, "A", links=[{"type": "tbd", "ref": "T1"}])
    _put(store, "B", relationships=[{"target": {"uid": "T1"}}])
    _put(store, "C", relationships=[{"uid": "T1"}])
    _put(store, "D", relationships=[{"ref": "T1"}])
    _put(store, "E", links=[{"type": "tbd", "ref": "OTHER"}], relationships=[{"uid": "OTHER"}])
    _put(store, "F", links=[{"type": "tbd", "ref": "T1"}], deleted=True)
    _put(store, "G", links=None, relationships=None)
    assert sorted(store.compute_affected_requirements("T1")) == ["A", "B", "C", "D"]


def test_defined_once():
    import inspect
    from reqtool import store as m
    src = inspect.getsource(m)
    assert src.count("def compute_affected_requirements") == 1
