"""SEC-17: /render/markdown must not return executable HTML."""
import pytest

PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "[x](javascript:alert(1))",
    "<a href=\"javascript:alert(1)\">x</a>",
    "<iframe src=\"https://evil.example\"></iframe>",
    "<svg onload=alert(1)>",
    "<div onclick=\"alert(1)\">x</div>",
]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_payloads_neutralised(client, payload):
    html = client.post("/render/markdown", json={"text": payload}).json()["html"].lower()
    for bad in ("<script", "onerror", "onload", "onclick", "javascript:", "<iframe"):
        assert bad not in html, (payload, html)


def test_normal_markdown_survives(client):
    md = "# Title\n\n**bold** and `code`\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```\nx = 1\n```\n\n[ok](https://example.com)"
    html = client.post("/render/markdown", json={"text": md}).json()["html"]
    for frag in ("<h1>", "<strong>bold</strong>", "<code>", "<table>", "<pre>", 'href="https://example.com"'):
        assert frag in html, frag
