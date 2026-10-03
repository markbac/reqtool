"""DAT-11: concurrent creates never share a human ID."""
import threading


def _create_many(store, n, req_type="functional"):
    ids, errors = [], []
    barrier = threading.Barrier(n)

    def work():
        try:
            barrier.wait()
            ids.append(store.create_requirement({"title": "t", "req_type": req_type})["id"])
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(repr(exc))

    threads = [threading.Thread(target=work) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return ids, errors


def test_20_parallel_creates_get_20_distinct_ids(store):
    ids, errors = _create_many(store, 20)
    assert errors == []
    assert len(ids) == 20 and len(set(ids)) == 20


def test_parallel_creates_across_types_stay_unique_per_type(store):
    a, ea = _create_many(store, 10, "functional")
    b, eb = _create_many(store, 10, "story")
    assert not ea and not eb
    assert len(set(a)) == 10 and len(set(b)) == 10


def test_next_id_reader_survives_concurrent_writes(store):
    stop = threading.Event()
    errors = []

    def reader():
        while not stop.is_set():
            try:
                store.next_id_for_type("functional")
            except Exception as exc:
                errors.append(repr(exc))
                return

    t = threading.Thread(target=reader)
    t.start()
    try:
        _create_many(store, 20)
    finally:
        stop.set()
        t.join()
    assert errors == []
