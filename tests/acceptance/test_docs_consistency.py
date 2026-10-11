"""Documentation must mention every operator-facing switch and the PDF guide must build."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "reqtool"


def test_every_reqtool_env_var_is_documented():
    used = set()
    for py in SRC.rglob("*.py"):
        used |= set(re.findall(r'["\'](REQTOOL_[A-Z_]+)["\']', py.read_text(encoding="utf-8")))
    guide = (ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
    missing = sorted(v for v in used if v not in guide)
    assert not missing, f"Undocumented environment variables: {missing}"


def test_user_guide_covers_auth_and_user_commands():
    guide = (ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
    for needle in ("--auth required", "reqtool user add", "SIG-v2", "approval_stale", "has_secret"):
        assert needle in guide, needle


def test_pdf_converter_renders_tables_and_angle_brackets():
    sys.path.insert(0, str(ROOT / "scripts"))
    from generate_pdf_guide import md_to_pdf_paragraphs
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import Table

    base = getSampleStyleSheet()
    styles = {k: base[k] for k in ("Heading1", "Heading2", "Heading3", "BodyText")}
    for k in ("Bullet", "Callout", "Code"):
        styles[k] = ParagraphStyle(k, parent=base["BodyText"])
    flow = md_to_pdf_paragraphs("| a | b |\n|---|---|\n| `x <y>` | 2 |\n\nSend `Bearer <token>` & go", styles)
    assert any(isinstance(f, Table) for f in flow)
    body = [f for f in flow if getattr(f, "text", "") and "&amp;" in f.text]
    assert body and "&lt;token&gt;" in body[0].text


def test_menu_entries_named_in_the_guide_exist_in_the_ui():
    """DOC-01: a path such as ``**⋯ More > Templates**`` must name a real menu entry."""
    guide = (ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
    header = (SRC / "ui" / "src" / "components" / "Header.jsx").read_text(encoding="utf-8")
    labels = re.findall(r"\*\*⋯ More > ([^*]+)\*\*", guide)
    assert labels, "the guide names no menu entries; the pattern needs updating"
    missing = sorted({lab for lab in labels if lab not in header})
    assert not missing, f"Menu entries in the guide that the UI does not have: {missing}"
