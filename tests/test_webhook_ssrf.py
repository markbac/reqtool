"""SEC-11: webhook targets are resolved and non-public addresses refused."""
import socket
import pytest
from reqtool.routers.deps import check_webhook_target


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/hook", "http://10.0.0.5/x", "http://192.168.1.2/", "http://172.16.0.1/",
    "http://[::1]/", "http://0.0.0.0/", "http://169.254.169.254/latest/meta-data",
    "http://metadata.google.internal/", "ftp://example.com/", "file:///etc/passwd",
])
def test_blocked_by_default(url):
    assert check_webhook_target(url) is not None


def test_hostname_resolving_to_private_is_blocked(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.1.2.3", 80))])
    assert "not public" in check_webhook_target("http://rebind.example.com/")


def test_any_private_answer_blocks(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [
        (2, 1, 6, "", ("93.184.216.34", 80)), (2, 1, 6, "", ("127.0.0.1", 80))])
    assert check_webhook_target("http://mixed.example.com/") is not None


def test_public_address_allowed(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    assert check_webhook_target("https://hooks.example.com/x") is None


def test_allow_private_permits_lan_but_never_metadata():
    assert check_webhook_target("http://127.0.0.1:9000/", allow_private=True) is None
    assert check_webhook_target("http://10.0.0.5/", allow_private=True) is None
    assert check_webhook_target("http://169.254.169.254/", allow_private=True) is not None
