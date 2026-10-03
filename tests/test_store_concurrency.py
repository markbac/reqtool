"""DAT-01: concurrent mutations must not lose updates."""
import threading

from reqtool.store import Store


def _run(n, fn):
    errors = []
    barrier = threading.Barrier(n)

    def worker(i):
        try:
            barrier.wait()
            fn(i)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors, errors


def _slow_disk(monkeypatch):
    """Widen the race window: a slow save lets other threads interleave."""
    import time
    from reqtool import store as store_mod
    real = store_mod.save_yaml

    def slow(path, data):
        time.sleep(0.005)
        real(path, data)

    monkeypatch.setattr(store_mod, "save_yaml", slow)


def test_concurrent_updates_all_recorded(store, monkeypatch):
    _slow_disk(monkeypatch)
    uid = store.create_requirement({"title": "T"})["uid"]
    n = 24
    _run(n, lambda i: store.update_requirement(uid, {"owner": f"o{i}"}, summary=f"u{i}"))
    hist = store.requirements[uid]["history"]
    assert len(hist) == n + 1
    assert {h["summary"] for h in hist} >= {f"u{i}" for i in range(n)}
    # what is on disk matches memory
    on_disk = Store(store.root)
    on_disk.load()
    assert len(on_disk.requirements[uid]["history"]) == n + 1


def test_every_mutator_holds_the_lock_while_writing(store, monkeypatch):
    """Deterministic guard: any save_yaml during a mutation must happen under the lock."""
    from reqtool import store as store_mod
    real = store_mod.save_yaml
    unlocked = []

    def checking(path, data):
        if not store._lock._is_owned():
            unlocked.append(str(path))
        real(path, data)

    monkeypatch.setattr(store_mod, "save_yaml", checking)
    uid = store.create_requirement({"title": "T"})["uid"]
    store.update_requirement(uid, {"title": "T2"})
    pid = store.create_principle({"title": "P", "content": {"description": "d", "rationale": "r",
                                                            "implications": "", "exceptions": ""}})["uid"]
    store.update_principle(pid, {"title": "P2"})
    tid = store.create_tbd({"title": "TBD"})["uid"]
    store.update_tbd(tid, {"title": "TBD2"})
    store.delete_tbd(tid)
    store.delete_principle(pid)
    store.delete_requirement(uid)
    assert unlocked == []


def test_reload_file_holds_lock_for_its_whole_body(store, monkeypatch):
    from reqtool import store as store_mod
    uid = store.create_requirement({"title": "T"})["uid"]
    seen = []
    real = store_mod.load_yaml

    def spy(path):
        seen.append(store._lock._is_owned())
        return real(path)

    monkeypatch.setattr(store_mod, "load_yaml", spy)
    store.reload_file(store.req_path(uid))
    assert seen and all(seen)


def test_concurrent_creates_are_all_persisted(store, monkeypatch):
    _slow_disk(monkeypatch)
    n = 20
    uids = []
    lock = threading.Lock()

    def make(i):
        u = store.create_requirement({"title": f"R{i}"})["uid"]
        with lock:
            uids.append(u)

    _run(n, make)
    assert len(set(uids)) == n
    reloaded = Store(store.root)
    reloaded.load()
    assert set(uids) <= set(reloaded.requirements)


def test_concurrent_update_and_delete_do_not_raise(store, monkeypatch):
    _slow_disk(monkeypatch)
    uid = store.create_requirement({"title": "T"})["uid"]

    def op(i):
        if i % 4 == 0:
            store.delete_requirement(uid)
        else:
            store.update_requirement(uid, {"owner": f"o{i}"})

    _run(16, op)
