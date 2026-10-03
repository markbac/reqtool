"""SEC-15: user-supplied IDs must not escape the repository."""
import pytest

from reqtool.fileio import InvalidId, validate_id


@pytest.mark.parametrize("v", ["p1", "iot-sensor", "v1.2", "A_b-c", "x" * 64])
def test_valid_ids(v):
    assert validate_id(v) == v


@pytest.mark.parametrize("v", ["", "../escape", "..", "a/b", "a\\b", "-x", ".hidden", "a b", "a\n", "x" * 65, "a..b", "/abs"])
def test_invalid_ids(v):
    with pytest.raises(InvalidId):
        validate_id(v)


@pytest.mark.parametrize("pid", ["../escape", "..", "a/../../b", "/tmp/abs", "a\\..\\b"])
def test_create_product_rejects_traversal(client, repo_root, pid):
    before = {p for p in repo_root.parent.iterdir()}
    r = client.post("/products", json={"id": pid})
    assert r.status_code == 422, r.text
    assert {p for p in repo_root.parent.iterdir()} == before
    assert not (repo_root / "products" / "_product.yaml").exists()


def test_create_product_ok(client, repo_root):
    r = client.post("/products", json={"id": "my-product", "title": "T"})
    assert r.status_code == 201
    assert (repo_root / "products" / "my-product" / "_product.yaml").exists()


def test_store_rejects_bad_module_and_product_ids(store):
    with pytest.raises(InvalidId):
        store.verify_module("p1", "../x")
    with pytest.raises(InvalidId):
        store.verify_module("../p", "m")
