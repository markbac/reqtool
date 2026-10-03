"""
reqtool.pdf
===========
PDF exporter engine for reqtool repositories using ReportLab.
Generates structured, professional PDF specifications with clickable internal links,
running headers/footers, bookmarks/outline, ATAM decision records, and repository descriptions.
"""

from __future__ import annotations

import io
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from reqtool import __version__

if TYPE_CHECKING:
    from .store import Store

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus.tableofcontents import TableOfContents

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fonts: DejaVu Sans is bundled and embedded (Latin, Greek, Cyrillic, many symbols). CJK text needs a
# TrueType font with glyph outlines, set with export.pdf.fallback_font or found on the system.
# ---------------------------------------------------------------------------
FONT_DIR = Path(__file__).parent / "defaults" / "fonts"
SANS, SANS_BOLD, SANS_ITALIC, SANS_BOLD_ITALIC = "ReqSans", "ReqSans-Bold", "ReqSans-Italic", "ReqSans-BoldItalic"
CJK_FONT = "ReqCJK"

_CJK_CANDIDATES = (
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
)
_CJK_RUN = re.compile(r"[\u1100-\u11ff\u2e80-\u9fff\uac00-\ud7af\uf900-\ufaff\uff00-\uffef]+")
_fonts_ready = False
_cjk_ready = False


def _register_fonts(fallback_font: str = "") -> bool:
    """Register the bundled fonts once and the CJK fallback if one can be embedded; True if CJK is available."""
    global _fonts_ready, _cjk_ready
    if not _fonts_ready:
        for name, file in ((SANS, "DejaVuSans.ttf"), (SANS_BOLD, "DejaVuSans-Bold.ttf"),
                           (SANS_ITALIC, "DejaVuSans-Oblique.ttf"), (SANS_BOLD_ITALIC, "DejaVuSans-BoldOblique.ttf")):
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
        pdfmetrics.registerFontFamily(SANS, normal=SANS, bold=SANS_BOLD, italic=SANS_ITALIC, boldItalic=SANS_BOLD_ITALIC)
        _fonts_ready = True
    if not _cjk_ready:
        for cand in ([fallback_font] if fallback_font else []) + list(_CJK_CANDIDATES):
            if not cand or not Path(cand).is_file():
                continue
            try:
                pdfmetrics.registerFont(TTFont(CJK_FONT, cand, subfontIndex=0))
                _cjk_ready = True
                break
            except Exception as exc:  # e.g. CFF-outline fonts (Noto CJK) cannot be embedded by ReportLab
                log.warning("PDF fallback font %s cannot be used: %s", cand, str(exc)[:120])
        if not _cjk_ready and fallback_font:
            log.warning("No usable CJK font for the PDF: set export.pdf.fallback_font to a TrueType (.ttf/.ttc) font")
    return _cjk_ready


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and draw 'Page X of Y' footers
    and running top headers across the entire document.
    """
    header_text = "reqtool Requirements Specification & Architecture Dossier"
    footer_text = "CONFIDENTIAL & PROPRIETARY \u2014 FOR INTERNAL USE ONLY"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super().showPage()
        super().save()

    def draw_header_footer(self, page_count: int):
        self.saveState()
        self.setFont(SANS, 8)
        self.setFillColor(colors.HexColor("#4b5563"))

        # Skip headers/footers on page 1 (cover)
        if self._pageNumber > 1:
            # Running Header
            self.drawString(54, 800, self.header_text)
            self.drawRightString(A4[0] - 54, 800, f"Page {self._pageNumber} of {page_count}")
            self.setStrokeColor(colors.HexColor("#d1d5db"))
            self.setLineWidth(0.5)
            self.line(54, 792, A4[0] - 54, 792)

            # Running Footer
            self.line(54, 45, A4[0] - 54, 45)
            self.drawString(54, 32, self.footer_text)
            self.drawRightString(A4[0] - 54, 32, f"reqtool v{__version__} \u2022 Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")

        self.restoreState()


class _SpecDocTemplate(SimpleDocTemplate):
    """Feeds every level-1 heading to the table of contents (with its page number) and the PDF outline."""

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name == "Heading1_Custom":
            text = flowable.getPlainText()
            key = f"toc-{self.page}-{abs(hash(text)) % 100000}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, 0, 0)
            self.notify("TOCEntry", (0, text, self.page, key))


def _clean_text(text: str) -> str:
    """Escape XML characters for ReportLab Paragraphs."""
    if not text:
        return ""
    text = str(text).replace("\ufe0f", "")  # emoji variation selector has no glyph
    escaped = (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
        .replace("\n", "<br/>")
    )
    if _cjk_ready:
        escaped = _CJK_RUN.sub(lambda m: f'<font name="{CJK_FONT}">{m.group(0)}</font>', escaped)
    return escaped


def source_revision(root: Path) -> str:
    """Describe the Git state the document was generated from, e.g. ``a1b2c3d4e5f6 (clean, baseline v1)``."""
    def git(*args: str) -> Optional[str]:
        try:
            res = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        return res.stdout.strip() if res.returncode == 0 else None

    sha = git("rev-parse", "--short=12", "HEAD")
    if not sha:
        return "not under version control"
    dirty = bool(git("status", "--porcelain"))
    baselines = [t[len("baseline/"):] for t in (git("tag", "--points-at", "HEAD") or "").split() if t.startswith("baseline/")]
    state = "uncommitted changes" if dirty else "clean"
    return f"{sha} ({state}" + (f", baseline {', '.join(baselines)}" if baselines else "") + ")"


def generate_pdf_bytes(store: "Store", product_id: Optional[str] = None) -> bytes:
    """Generate complete PDF specification bytes for a given store."""
    buffer = io.BytesIO()
    pdf_cfg = store.config.export.pdf
    _register_fonts(pdf_cfg.fallback_font)

    # Document setup: A4 size, 0.75 in (54 pt) margins
    doc = _SpecDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    styles = getSampleStyleSheet()
    
    # Custom Palette
    PRIMARY = colors.HexColor("#1e3a8a")     # Deep blue
    SECONDARY = colors.HexColor("#0f766e")   # Teal
    ACCENT = colors.HexColor("#b45309")      # Amber
    TEXT_DARK = colors.HexColor("#1f2937")   # Dark gray
    BG_LIGHT = colors.HexColor("#f8fafc")    # Off-white
    BORDER_COLOR = colors.HexColor("#cbd5e1")

    # Custom Typography Styles
    style_cover_title = ParagraphStyle(
        "CoverTitle",
        parent=styles["Normal"],
        fontName=SANS_BOLD,
        fontSize=24,
        leading=30,
        textColor=PRIMARY,
        alignment=TA_LEFT,
        spaceAfter=10,
    )
    style_cover_subtitle = ParagraphStyle(
        "CoverSubtitle",
        parent=styles["Normal"],
        fontName=SANS,
        fontSize=12,
        leading=16,
        textColor=SECONDARY,
        spaceAfter=20,
    )
    style_h1 = ParagraphStyle(
        "Heading1_Custom",
        parent=styles["Normal"],
        fontName=SANS_BOLD,
        fontSize=16,
        leading=20,
        textColor=PRIMARY,
        spaceBefore=18,
        spaceAfter=8,
        keepWithNext=True,
    )
    style_h2 = ParagraphStyle(
        "Heading2_Custom",
        parent=styles["Normal"],
        fontName=SANS_BOLD,
        fontSize=12,
        leading=16,
        textColor=SECONDARY,
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True,
    )
    style_body = ParagraphStyle(
        "Body_Custom",
        parent=styles["Normal"],
        fontName=SANS,
        fontSize=9.5,
        leading=13.5,
        textColor=TEXT_DARK,
        spaceAfter=6,
    )
    style_body_bold = ParagraphStyle(
        "Body_Bold",
        parent=style_body,
        fontName=SANS_BOLD,
    )
    style_meta_label = ParagraphStyle(
        "MetaLabel",
        parent=styles["Normal"],
        fontName=SANS_BOLD,
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#4b5563"),
    )
    style_meta_val = ParagraphStyle(
        "MetaVal",
        parent=styles["Normal"],
        fontName=SANS,
        fontSize=8.5,
        leading=11,
        textColor=TEXT_DARK,
    )
    style_toc_item = ParagraphStyle(
        "TOCItem",
        parent=styles["Normal"],
        fontName=SANS,
        fontSize=10,
        leading=14,
        textColor=PRIMARY,
    )

    story = []

    # Map requirement UIDs to IDs for internal link resolution
    uid_to_id = {r["uid"]: r.get("id", "") for r in store.requirements.values()}

    repo_title = store.config.repo_title or store.config.repo_id or "Requirements Repository"
    repo_desc = (
        getattr(store.config, "repo_description", "")
        or "This document contains the complete specifications, principles, architecture decisions (ATAM), reusable modules, and product line manifests."
    )

    # =========================================================================
    # COVER / HEADER BLOCK
    # =========================================================================
    story.append(Paragraph(_clean_text(repo_title), style_cover_title))
    story.append(Paragraph("Full System Specification & Architecture Specification Dossier", style_cover_subtitle))
    story.append(HRFlowable(width="100%", thickness=2, color=PRIMARY, spaceAfter=15))

    # Overarching Repo Description Box
    desc_p = Paragraph(f"<b>Repository Overview & Context:</b><br/>{_clean_text(repo_desc)}", style_body)
    desc_table = Table([[desc_p]], colWidths=[500])
    desc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
        ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(desc_table)
    story.append(Spacer(1, 15))

    # Executive Summary Metadata Grid
    req_list = [r for r in store.requirements.values() if not r.get("deleted")]
    principle_list = [p for p in store.principles.values() if not p.get("deleted")]
    decision_list = [d for d in store.decisions.values() if not d.get("deleted")]
    tbd_list = [t for t in store.decisions.values() if not t.get("deleted")]
    module_list = list(store.modules.values())
    product_list = list(store.products.values())

    meta_grid_data = [
        [Paragraph("<b>Export Date:</b>", style_meta_label), Paragraph(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), style_meta_val),
         Paragraph("<b>reqtool Version:</b>", style_meta_label), Paragraph(f"v{__version__}", style_meta_val)],
        [Paragraph("<b>Requirements:</b>", style_meta_label), Paragraph(str(len(req_list)), style_meta_val),
         Paragraph("<b>Principles:</b>", style_meta_label), Paragraph(str(len(principle_list)), style_meta_val)],
        [Paragraph("<b>Decisions (ADRs):</b>", style_meta_label), Paragraph(str(len(decision_list)), style_meta_val),
         Paragraph("<b>Open TBDs:</b>", style_meta_label), Paragraph(str(len(tbd_list)), style_meta_val)],
        [Paragraph("<b>Reusable Modules:</b>", style_meta_label), Paragraph(str(len(module_list)), style_meta_val),
         Paragraph("<b>Product Variants:</b>", style_meta_label), Paragraph(str(len(product_list)), style_meta_val)],
        [Paragraph("<b>Source Revision:</b>", style_meta_label),
         Paragraph(_clean_text(source_revision(store.root)), style_meta_val), "", ""],
    ]
    meta_table = Table(meta_grid_data, colWidths=[110, 140, 110, 140])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('SPAN', (1, 4), (3, 4)),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 20))

    # =========================================================================
    # TABLE OF CONTENTS
    # =========================================================================
    story.append(Paragraph("Table of Contents", style_h2))
    toc = TableOfContents()
    toc.levelStyles = [style_toc_item]
    story.append(toc)
    story.append(Spacer(1, 25))

    # =========================================================================
    # SECTION 1: PRINCIPLES
    # =========================================================================
    story.append(Paragraph('<a name="section-principles"/>1. Architecture & Engineering Principles', style_h1))
    story.append(HRFlowable(width="100%", thickness=1, color=SECONDARY, spaceAfter=10))

    if not principle_list:
        story.append(Paragraph("<i>No architecture principles recorded.</i>", style_body))
    else:
        for p in sorted(principle_list, key=lambda x: x.get("id", "")):
            pid = _clean_text(p.get("id", ""))
            title = _clean_text(p.get("title", ""))
            content = p.get("content", {})
            
            p_elem = []
            p_elem.append(Paragraph(f'<a name="principle-{pid}"/><b>{pid}</b> — {title}', style_h2))
            if content.get("description"):
                p_elem.append(Paragraph(f"<b>Statement:</b> {_clean_text(content['description'])}", style_body))
            if content.get("rationale"):
                p_elem.append(Paragraph(f"<b>Rationale:</b> {_clean_text(content['rationale'])}", style_body))
            if content.get("implications"):
                p_elem.append(Paragraph(f"<b>Implications:</b> {_clean_text(content['implications'])}", style_body))
            p_elem.append(Spacer(1, 6))
            story.append(KeepTogether(p_elem))

    story.append(Spacer(1, 15))

    # =========================================================================
    # SECTION 2: ARCHITECTURE DECISION RECORDS (ADRS & ATAM)
    # =========================================================================
    story.append(Paragraph('<a name="section-decisions"/>2. Architecture Decision Records (ADRs with ATAM)', style_h1))
    story.append(HRFlowable(width="100%", thickness=1, color=SECONDARY, spaceAfter=10))

    if not decision_list:
        story.append(Paragraph("<i>No architecture decisions recorded.</i>", style_body))
    else:
        for d in sorted(decision_list, key=lambda x: x.get("id", "")):
            did = _clean_text(d.get("id", ""))
            title = _clean_text(d.get("title", ""))
            status = _clean_text((d.get("status") or "proposed").capitalize())
            owner = _clean_text(d.get("owner") or "Unassigned")
            content = d.get("content", {})

            d_elems = []
            d_elems.append(Paragraph(f'<a name="dec-{did}"/><b>{did}: {title}</b>', style_h2))
            
            # Metadata row
            meta_str = f"<b>Status:</b> {status} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Owner:</b> {owner}"
            if d.get("supersedes"):
                meta_str += f" &nbsp;&nbsp;|&nbsp;&nbsp; <b>Supersedes:</b> {d['supersedes']}"
            d_elems.append(Paragraph(meta_str, style_body))

            if content.get("context") or content.get("description"):
                ctx = content.get("context") or content.get("description")
                d_elems.append(Paragraph(f"<b>Context & Problem:</b> {_clean_text(ctx)}", style_body))

            options = content.get("options", [])
            if options:
                opts_text = "<b>Considered Options:</b><br/>"
                for opt in options:
                    opt_name = opt.get("name", "") if isinstance(opt, dict) else str(opt)
                    opts_text += f"• <b>{_clean_text(opt_name)}</b>"
                    if isinstance(opt, dict) and opt.get("pros"):
                        opts_text += f" (Pros: {', '.join(_clean_text(p) for p in opt['pros'])})"
                    opts_text += "<br/>"
                d_elems.append(Paragraph(opts_text, style_body))

            if content.get("chosen_option") or content.get("rationale"):
                d_elems.append(Paragraph(f"<b>Decision & Rationale:</b> {_clean_text(content.get('chosen_option', ''))} — {_clean_text(content.get('rationale', ''))}", style_body))

            # ATAM Details
            atam = content.get("atam")
            if atam and isinstance(atam, dict) and atam.get("enabled", True):
                atam_lines = ["<b>ATAM Tradeoff Analysis:</b>"]
                if atam.get("quality_attributes"):
                    atam_lines.append(f"• <b>Quality Attributes:</b> {', '.join(_clean_text(q) for q in atam['quality_attributes'])}")
                for s in atam.get("sensitivity_points", []):
                    atam_lines.append(f"• <b>Sensitivity [{_clean_text(s.get('attribute',''))}]:</b> {_clean_text(s.get('description',''))}")
                for t in atam.get("tradeoff_points", []):
                    attrs = ", ".join(s for s in t.get("attributes", []))
                    atam_lines.append(f"• <b>Tradeoff [{attrs}]:</b> {_clean_text(t.get('description',''))}")
                for r in atam.get("risks", []):
                    atam_lines.append(f"• <font color='#b45309'><b>Risk ⚠️:</b></font> {_clean_text(r)}")
                for nr in atam.get("non_risks", []):
                    atam_lines.append(f"• <font color='#15803d'><b>Non-Risk ✅:</b></font> {_clean_text(nr)}")
                
                d_elems.append(Paragraph("<br/>".join(atam_lines), style_body))

            d_elems.append(Spacer(1, 10))
            story.append(KeepTogether(d_elems))

    story.append(Spacer(1, 15))

    # =========================================================================
    # SECTION 3: REQUIREMENTS SPECIFICATION
    # =========================================================================
    story.append(Paragraph('<a name="section-requirements"/>3. Requirements Specification', style_h1))
    story.append(HRFlowable(width="100%", thickness=1, color=SECONDARY, spaceAfter=10))

    # Group by Domain
    by_domain: dict[str, list] = {}
    for r in sorted(req_list, key=lambda x: x.get("id", "")):
        dom = (r.get("domain") or "system").capitalize()
        by_domain.setdefault(dom, []).append(r)

    for domain_name, domain_reqs in sorted(by_domain.items()):
        story.append(Paragraph(f"Domain: {domain_name}", style_h2))

        for r in domain_reqs:
            rid = _clean_text(r.get("id", ""))
            rtitle = _clean_text(r.get("title", ""))
            status = _clean_text(r.get("status", ""))
            priority = _clean_text(r.get("priority", ""))
            req_type = _clean_text(r.get("req_type", ""))
            owner = _clean_text(r.get("owner", "") or "Unassigned")
            desc = _clean_text(r.get("content", {}).get("description", ""))
            rationale = _clean_text(r.get("content", {}).get("rationale", ""))

            r_block = []
            # Header with clickable target
            r_block.append(Paragraph(f'<a name="req-{rid}"/><b>[{rid}] {rtitle}</b>', ParagraphStyle(
                "ReqHeader", parent=styles["Normal"], fontName=SANS_BOLD, fontSize=11, leading=14, textColor=PRIMARY
            )))

            # Metadata Table
            meta_row1 = [
                Paragraph(f"<b>Type:</b> {req_type}", style_meta_val),
                Paragraph(f"<b>Status:</b> {status}", style_meta_val),
                Paragraph(f"<b>Priority:</b> {priority}", style_meta_val),
                Paragraph(f"<b>Owner:</b> {owner}", style_meta_val),
            ]
            req_table = Table([meta_row1], colWidths=[125, 125, 125, 125])
            req_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ('PADDING', (0, 0), (-1, -1), 4),
            ]))
            r_block.append(req_table)
            r_block.append(Spacer(1, 4))

            if desc:
                r_block.append(Paragraph(f"<b>Description:</b> {desc}", style_body))
            if rationale:
                r_block.append(Paragraph(f"<b>Rationale:</b> {rationale}", style_body))

            # Acceptance Criteria
            acs = r.get("acceptance_criteria", [])
            if acs:
                ac_lines = ["<b>Acceptance Criteria:</b>"]
                for ac in acs:
                    ac_id = _clean_text(ac.get("id", ""))
                    ac_text = _clean_text(ac.get("text", ""))
                    ac_lines.append(f"• <code>{ac_id}</code>: {ac_text}")
                r_block.append(Paragraph("<br/>".join(ac_lines), style_body))

            # Internal Clickable Relationships
            rels = r.get("relationships", [])
            parent_uid = r.get("parentId")
            rel_links = []

            if parent_uid and parent_uid in uid_to_id:
                parent_id = uid_to_id[parent_uid]
                rel_links.append(f'Parent → <a href="#req-{parent_id}" color="#1e3a8a"><u><b>{parent_id}</b></u></a>')

            for rel in rels:
                t_uid = rel.get("target", {}).get("uid", "")
                t_type = rel.get("type", "relates_to")
                if t_uid in uid_to_id:
                    t_id = uid_to_id[t_uid]
                    rel_links.append(f'{t_type} → <a href="#req-{t_id}" color="#1e3a8a"><u><b>{t_id}</b></u></a>')

            if rel_links:
                r_block.append(Paragraph(f"<b>Traceability Links:</b> { ' &nbsp;|&nbsp; '.join(rel_links) }", style_body))

            r_block.append(Spacer(1, 8))
            story.append(KeepTogether(r_block))

    story.append(Spacer(1, 15))

    # =========================================================================
    # SECTION 4: REUSABLE MODULES
    # =========================================================================
    story.append(Paragraph('<a name="section-modules"/>4. Reusable Subsystem Modules', style_h1))
    story.append(HRFlowable(width="100%", thickness=1, color=SECONDARY, spaceAfter=10))

    if not module_list:
        story.append(Paragraph("<i>No reusable modules registered.</i>", style_body))
    else:
        for mod in module_list:
            mid = _clean_text(mod.get("id", ""))
            mtitle = _clean_text(mod.get("name") or mod.get("title") or mid)
            mver = _clean_text(mod.get("version", "1.0.0"))
            mdesc = _clean_text(mod.get("description", ""))

            m_elems = []
            m_elems.append(Paragraph(f'<b>Module: {mid}</b> ({mtitle}) — v{mver}', style_h2))
            if mdesc:
                m_elems.append(Paragraph(f"<b>Description:</b> {mdesc}", style_body))
            m_elems.append(Spacer(1, 6))
            story.append(KeepTogether(m_elems))

    story.append(Spacer(1, 15))

    # =========================================================================
    # SECTION 5: PRODUCT LINE MANIFESTS
    # =========================================================================
    story.append(Paragraph('<a name="section-products"/>5. Product Line Manifests', style_h1))
    story.append(HRFlowable(width="100%", thickness=1, color=SECONDARY, spaceAfter=10))

    if not product_list:
        story.append(Paragraph("<i>No product line manifests registered.</i>", style_body))
    else:
        for prod in product_list:
            pid = _clean_text(prod.get("id", ""))
            pname = _clean_text(prod.get("name") or prod.get("title") or pid)
            pdesc = _clean_text(prod.get("description", ""))
            mods = prod.get("modules", [])

            p_elems = []
            p_elems.append(Paragraph(f'<b>Product Line: {pname}</b> (<code>{pid}</code>)', style_h2))
            if pdesc:
                p_elems.append(Paragraph(f"<b>Description:</b> {pdesc}", style_body))
            if mods:
                mod_names = ", ".join(_clean_text(m.get("id", "")) for m in mods)
                p_elems.append(Paragraph(f"<b>Included Modules:</b> {mod_names}", style_body))
            p_elems.append(Spacer(1, 6))
            story.append(KeepTogether(p_elems))

    story.append(Spacer(1, 15))

    # =========================================================================
    # SECTION 6: OPEN QUESTIONS & TBDS
    # =========================================================================
    story.append(Paragraph('<a name="section-tbds"/>6. Open Questions & Pending Decisions (TBDs)', style_h1))
    story.append(HRFlowable(width="100%", thickness=1, color=SECONDARY, spaceAfter=10))

    if not tbd_list:
        story.append(Paragraph("<i>No open TBDs in repository.</i>", style_body))
    else:
        for t in sorted(tbd_list, key=lambda x: x.get("id", "")):
            tid = _clean_text(t.get("id", ""))
            ttitle = _clean_text(t.get("title", ""))
            tstatus = _clean_text(t.get("status", "open"))
            towner = _clean_text(t.get("owner", "Unassigned"))
            tdesc = _clean_text(t.get("content", {}).get("description", ""))

            t_elems = []
            t_elems.append(Paragraph(f'<a name="tbd-{tid}"/><b>[{tid}] {ttitle}</b>', style_h2))
            t_elems.append(Paragraph(f"<b>Status:</b> {tstatus} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Owner:</b> {towner}", style_body))
            if tdesc:
                t_elems.append(Paragraph(f"<b>Description:</b> {tdesc}", style_body))
            t_elems.append(Spacer(1, 6))
            story.append(KeepTogether(t_elems))

    # Build Document
    canvas_cls = type("ConfiguredCanvas", (NumberedCanvas,), {
        "header_text": pdf_cfg.header_text, "footer_text": pdf_cfg.footer_text})
    doc.multiBuild(story, canvasmaker=canvas_cls)
    return buffer.getvalue()
