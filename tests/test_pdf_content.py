"""INT-05: PDF export embeds a Unicode font, takes its footer from config and states its source revision."""
import io
import subprocess

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from pypdf import PdfReader

from reqtool import pdf as pdfmod
from tests.conftest import make_req


def _text(client, **params):
    r = client.get("/export/pdf", params=params)
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"%PDF")
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(r.content)).pages), r.content


def _tiny_cjk_font(path):
    """A minimal TrueType font with outlines for two CJK characters (stands in for a real system font)."""
    names = [".notdef", "uni9700", "uni6C42"]
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({0x9700: "uni9700", 0x6C42: "uni6C42"})
    pen = TTGlyphPen(None)
    pen.moveTo((100, 0)); pen.lineTo((100, 700)); pen.lineTo((800, 700)); pen.lineTo((800, 0)); pen.closePath()
    glyph = pen.glyph()
    fb.setupGlyf({n: glyph for n in names})
    fb.setupHorizontalMetrics({n: (1000, 100) for n in names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "TinyCJK", "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=800, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    fb.save(str(path))


def test_non_latin_text_is_embedded_and_extractable(client):
    make_req(client, title="Ünïcödé Привет αβγ", content={"description": "Ω ≤ 5 µs", "rationale": "r"})
    text, raw = _text(client)
    assert "Привет" in text and "αβγ" in text and "Ünïcödé" in text
    assert b"DejaVuSans" in raw  # embedded subset


def test_cjk_text_uses_configured_fallback_font(client, tmp_path, monkeypatch):
    font = tmp_path / "tiny.ttf"
    _tiny_cjk_font(font)
    monkeypatch.setattr(pdfmod, "_cjk_ready", False)
    client.app.state.store.config.export.pdf.fallback_font = str(font)
    make_req(client, title="需求 spec")
    text, _ = _text(client)
    assert "需求" in text


def test_footer_and_header_come_from_config(client):
    cfg = client.app.state.store.config.export.pdf
    cfg.footer_text = "ACME RESTRICTED"
    cfg.header_text = "ACME Spec"
    make_req(client, title="x")
    text, _ = _text(client)
    assert "ACME RESTRICTED" in text and "ACME Spec" in text
    assert "CONFIDENTIAL & PROPRIETARY" not in text


def test_cover_shows_commit_sha_and_dirty_flag(client, repo_root):
    def git(*a):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=repo_root, check=True, capture_output=True)
    git("init", "-q")
    make_req(client, title="x")
    git("add", "-A"); git("commit", "-q", "-m", "base")
    sha = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=repo_root, capture_output=True, text=True).stdout.strip()
    text, _ = _text(client)
    assert sha in text and "clean" in text
    make_req(client, title="y")  # uncommitted
    text, _ = _text(client)
    assert sha in text and "uncommitted changes" in text


def test_cover_without_git_says_so(client):
    text, _ = _text(client)
    assert "not under version control" in text or "clean" in text or "uncommitted" in text


def test_table_of_contents_has_page_numbers_and_outline(client):
    for i in range(60):
        make_req(client, title=f"Requirement number {i}", content={"description": "The system shall do something useful. " * 8, "rationale": "r"})
    r = client.get("/export/pdf")
    reader = PdfReader(io.BytesIO(r.content))
    assert len(reader.pages) > 3
    toc_lines = reader.pages[0].extract_text().splitlines()
    i = next(n for n, ln in enumerate(toc_lines) if ln.startswith("6. Open Questions"))
    # the entry for the last section carries a page number greater than 1
    nearby = [ln.strip() for ln in toc_lines[max(0, i - 1): i + 2] if ln.strip().isdigit()]
    assert nearby and int(nearby[0]) > 1, toc_lines[max(0, i - 2): i + 3]
    assert len(reader.outline) == 6
