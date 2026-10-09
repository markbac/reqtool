"""SEC-19: PUT /config only accepts settings that exist in the config model."""


def test_unknown_top_level_key_422_and_not_persisted(client):
    r = client.put("/config", json={"auth": {"mode": "off"}, "repo_title": "T"})
    assert r.status_code == 422
    assert "auth" in r.json()["detail"]["message"]
    assert client.get("/config").json()["repo_title"] == ""
    cfg = client.app.state.store.root / ".reqtool" / "config.yaml"
    assert not cfg.exists() or "auth" not in cfg.read_text()


def test_unknown_nested_key_422(client):
    r = client.put("/config", json={"git": {"commit_name": "x", "hooks": "rm -rf /"}})
    assert r.status_code == 422 and "git.hooks" in r.json()["detail"]["message"]
    r = client.put("/config", json={"webhooks": [{"url": "http://example.com", "exec": "x"}]})
    assert r.status_code == 422 and "webhooks[0].exec" in r.json()["detail"]["message"]


def test_known_settings_still_save(client):
    r = client.put("/config", json={"repo_title": "My repo", "git": {"commit_name": "Ann"}})
    assert r.status_code == 200
    assert r.json()["repo_title"] == "My repo" and r.json()["git"]["commit_name"] == "Ann"
