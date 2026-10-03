"""SEC-16: webhook secrets are write-only over the API."""
import yaml

SECRET = "s3cr3t-value-123"


def _add(client):
    r = client.post("/webhooks", json={"url": "https://example.com/h", "secret": SECRET})
    assert r.status_code == 201, r.text
    return r


def test_post_get_config_never_return_secret(client):
    r = _add(client)
    assert SECRET not in r.text and r.json()["has_secret"] is True
    for path in ("/webhooks", "/config"):
        resp = client.get(path)
        assert SECRET not in resp.text, path
    assert client.get("/webhooks").json()[0]["has_secret"] is True


def test_secret_still_stored_and_used(client, repo_root):
    _add(client)
    cfg = yaml.safe_load((repo_root / ".reqtool" / "config.yaml").read_text())
    assert cfg["webhooks"][0]["secret"] == SECRET


def test_round_trip_of_redacted_config_keeps_secret(client, repo_root):
    _add(client)
    cfg = client.get("/config").json()
    assert cfg["webhooks"][0]["secret"] != SECRET
    r = client.put("/config", json={"webhooks": cfg["webhooks"]})
    assert r.status_code == 200, r.text
    assert SECRET not in r.text
    stored = yaml.safe_load((repo_root / ".reqtool" / "config.yaml").read_text())
    assert stored["webhooks"][0]["secret"] == SECRET
    assert "has_secret" not in stored["webhooks"][0]


def test_hook_without_secret(client):
    r = client.post("/webhooks", json={"url": "https://example.com/x"})
    assert r.json()["has_secret"] is False and r.json()["secret"] is None
