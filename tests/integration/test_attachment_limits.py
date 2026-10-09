"""SEC-09: upload size limit, header parsing and per-item cap."""
import pytest
from tests.conftest import make_req
from reqtool.routers import attachments


def _up(client, uid, data=b"hello", disp='attachment; filename="a.txt"', base="requirements"):
    return client.post(f"/{base}/{uid}/attachments", content=data,
                       headers={"Content-Disposition": disp, "Content-Type": "application/octet-stream"})


def test_oversize_body_413_and_nothing_written(client, monkeypatch):
    monkeypatch.setenv("REQTOOL_MAX_UPLOAD_MB", "0.001")  # ~1 KB
    uid = make_req(client)["uid"]
    r = _up(client, uid, b"x" * 5000)
    assert r.status_code == 413
    assert client.get(f"/requirements/{uid}/attachments").json() == []
    assert not client.app.state.store.attachment_dir(uid).exists() or not any(client.app.state.store.attachment_dir(uid).iterdir())


def test_within_limit_ok_on_both_routes(client, monkeypatch):
    monkeypatch.setenv("REQTOOL_MAX_UPLOAD_MB", "1")
    uid = make_req(client)["uid"]
    assert _up(client, uid).status_code == 201
    assert _up(client, uid, base="artefacts", disp='attachment; filename="b.txt"').status_code == 201


def test_oversize_declared_length_rejected_before_reading(client, monkeypatch):
    monkeypatch.setenv("REQTOOL_MAX_UPLOAD_MB", "0.001")
    uid = make_req(client)["uid"]
    r = client.post(f"/requirements/{uid}/attachments", content=b"y" * 3000,
                    headers={"Content-Disposition": 'attachment; filename="a.txt"'})
    assert r.status_code == 413


@pytest.mark.parametrize("disp,expected", [
    ('attachment; filename="report v2.pdf"', "report v2.pdf"),
    ("attachment; filename=plain.txt", "plain.txt"),
    ('attachment; filename="a;b.txt"; size=3', "a_b.txt"),
    ('attachment; filename="../../etc/passwd"', "passwd"),
    ("", "attachment"),
])
def test_filename_parsing(client, disp, expected):
    uid = make_req(client)["uid"]
    r = _up(client, uid, disp=disp)
    assert r.status_code == 201, r.text
    assert r.json()["filename"] == expected


def test_per_item_cap_allows_overwrite(client, monkeypatch):
    monkeypatch.setattr(attachments, "MAX_ATTACHMENTS_PER_ARTEFACT", 2)
    uid = make_req(client)["uid"]
    assert _up(client, uid, disp='attachment; filename="1.txt"').status_code == 201
    assert _up(client, uid, disp='attachment; filename="2.txt"').status_code == 201
    assert _up(client, uid, disp='attachment; filename="3.txt"').status_code == 409
    assert _up(client, uid, disp='attachment; filename="2.txt"').status_code == 201  # replace
