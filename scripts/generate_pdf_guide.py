#!/usr/bin/env python3
"""
scripts/generate_pdf_guide.py
==============================
Generates a professional, publication-quality PDF User Guide and Technical Manual
for reqtool (reqtool-user-guide.pdf) using ReportLab.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

ROOT = Path(__file__).parent.parent
DOCS_DIR = ROOT / "docs"
OUTPUT_PDF = ROOT / "reqtool-user-guide.pdf"


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and render total page count & running headers/footers."""
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        if self._pageNumber == 1:
            # Suppress header and footer on cover page
            return

        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#8b949e"))

        # Running Header
        self.drawString(54, 750, "reqtool — Requirements Management & OpenAPI 3.1 Specification")
        self.setStrokeColor(colors.HexColor("#30363d"))
        self.setLineWidth(0.5)
        self.line(54, 742, 558, 742)

        # Running Footer
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 36, page_str)
        self.drawString(54, 36, "Confidential & Proprietary — reqtool Documentation")
        self.line(54, 48, 558, 48)

        self.restoreState()


def md_to_pdf_paragraphs(text: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    """Parse Markdown text into ReportLab Flowable objects."""
    flowables = []
    lines = text.split("\n")
    in_code_block = False
    code_lines = []

    for line in lines:
        raw_line = line.rstrip()

        # Code block handling
        if raw_line.startswith("```"):
            if in_code_block:
                code_text = "\n".join(code_lines).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                p = Paragraph(f"<font name='Courier' size=8>{code_text.replace('\n', '<br/>')}</font>", styles["Code"])
                flowables.append(p)
                flowables.append(Spacer(1, 6))
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(raw_line)
            continue

        if not raw_line.strip():
            flowables.append(Spacer(1, 4))
            continue

        # Headings
        if raw_line.startswith("# "):
            title = raw_line[2:].strip()
            flowables.append(Spacer(1, 10))
            flowables.append(Paragraph(title, styles["Heading1"]))
            flowables.append(Spacer(1, 6))
        elif raw_line.startswith("## "):
            title = raw_line[3:].strip()
            flowables.append(Spacer(1, 8))
            flowables.append(Paragraph(title, styles["Heading2"]))
            flowables.append(Spacer(1, 4))
        elif raw_line.startswith("### "):
            title = raw_line[4:].strip()
            flowables.append(Spacer(1, 6))
            flowables.append(Paragraph(title, styles["Heading3"]))
            flowables.append(Spacer(1, 3))
        elif raw_line.startswith("- ") or raw_line.startswith("* "):
            item = raw_line[2:].strip()
            item_formatted = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', item)
            item_formatted = re.sub(r'`(.*?)`', r'<font name="Courier">\1</font>', item_formatted)
            flowables.append(Paragraph(f"• {item_formatted}", styles["Bullet"]))
        elif raw_line.startswith("> "):
            quote = raw_line[2:].strip()
            flowables.append(Paragraph(f"<i>{quote}</i>", styles["Callout"]))
            flowables.append(Spacer(1, 4))
        else:
            p_formatted = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', raw_line)
            p_formatted = re.sub(r'`(.*?)`', r'<font name="Courier">\1</font>', p_formatted)
            flowables.append(Paragraph(p_formatted, styles["BodyText"]))

    return flowables


def build_pdf():
    print(f"Generating PDF User Guide: {OUTPUT_PDF}")

    doc = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    base_styles = getSampleStyleSheet()

    styles = {
        "CoverTitle": ParagraphStyle(
            "CoverTitle",
            parent=base_styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=34,
            textColor=colors.HexColor("#0969da"),
            alignment=0,
            spaceAfter=12
        ),
        "CoverSubtitle": ParagraphStyle(
            "CoverSubtitle",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=13,
            leading=18,
            textColor=colors.HexColor("#57606a"),
            spaceAfter=24
        ),
        "Heading1": ParagraphStyle(
            "H1",
            parent=base_styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0969da"),
            spaceBefore=14,
            spaceAfter=8,
            keepWithNext=True
        ),
        "Heading2": ParagraphStyle(
            "H2",
            parent=base_styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#1f2328"),
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True
        ),
        "Heading3": ParagraphStyle(
            "H3",
            parent=base_styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#24292f"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True
        ),
        "BodyText": ParagraphStyle(
            "Body",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            textColor=colors.HexColor("#24292f"),
            spaceAfter=6
        ),
        "Bullet": ParagraphStyle(
            "Bullet",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            leftIndent=14,
            textColor=colors.HexColor("#24292f"),
            spaceAfter=3
        ),
        "Code": ParagraphStyle(
            "CodeBlock",
            parent=base_styles["Code"],
            fontName="Courier",
            fontSize=8,
            leading=10.5,
            backColor=colors.HexColor("#f6f8fa"),
            borderColor=colors.HexColor("#d0d7de"),
            borderWidth=0.5,
            borderPadding=8,
            spaceAfter=8
        ),
        "Callout": ParagraphStyle(
            "Callout",
            parent=base_styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            leading=13,
            backColor=colors.HexColor("#ddf4ff"),
            borderColor=colors.HexColor("#54aef7"),
            borderWidth=0.5,
            borderPadding=6,
            spaceAfter=6
        )
    }

    story = []

    # Cover Page
    story.append(Spacer(1, 40))
    story.append(Paragraph("reqtool User Guide &amp;<br/>Technical Reference Manual", styles["CoverTitle"]))
    story.append(Paragraph("Git-Backed Requirements Management System &amp; OpenAPI 3.1 REST API", styles["CoverSubtitle"]))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#0969da"), spaceAfter=20))

    # Meta Table
    meta_data = [
        [Paragraph("<b>Document Version:</b>", styles["BodyText"]), Paragraph("0.4.2", styles["BodyText"])],
        [Paragraph("<b>Publication Date:</b>", styles["BodyText"]), Paragraph("October 2026", styles["BodyText"])],
        [Paragraph("<b>Compliance Standards:</b>", styles["BodyText"]), Paragraph("21 CFR Part 11, ISO 26262, OMG ReqIF 1.2, OpenAPI 3.1", styles["BodyText"])],
        [Paragraph("<b>Target Audience:</b>", styles["BodyText"]), Paragraph("Systems Engineers, Lead Developers, QA &amp; Compliance Managers", styles["BodyText"])],
    ]
    t = Table(meta_data, colWidths=[140, 360])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f6f8fa')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#d0d7de')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e1e4e8')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 40))

    # Executive Overview
    story.append(Paragraph("Executive Overview", styles["Heading1"]))
    story.append(Paragraph(
        "<b>reqtool</b> is an enterprise-grade requirements management system built on top of standard Git workflows and YAML 1.2 files. "
        "It provides full cryptographic traceability, audit versioning, AI duplicate detection, automated event-driven workflow rules, "
        "and compliance exporters for ISO 26262 and 21 CFR Part 11 regulatory audits.",
        styles["BodyText"]
    ))

    story.append(PageBreak())

    # Document Section Mapping
    sections = [
        ("1. Overview & Quickstart", ROOT / "README.md"),
        ("2. Comprehensive User Guide", DOCS_DIR / "USER_GUIDE.md"),
        ("3. Product Datasheet & Technical Specifications", DOCS_DIR / "PRODUCT_DATASHEET.md"),
        ("4. System Architecture & Design Specification", DOCS_DIR / "ARCHITECTURE.md"),
        ("5. Requirements Engineering Philosophy", DOCS_DIR / "REQUIREMENTS_PHILOSOPHY.md"),
        ("6. Standalone Binaries & Deployment Guide", DOCS_DIR / "STANDALONE_EXE_GUIDE.md"),
        ("7. Git LFS & Binary Attachment Best Practices", DOCS_DIR / "GIT_ATTACHMENT_BEST_PRACTICES.md"),
    ]

    for sec_title, sec_file in sections:
        if not sec_file.exists():
            continue
        story.append(Paragraph(sec_title, styles["Heading1"]))
        text = sec_file.read_text(encoding="utf-8")
        flowables = md_to_pdf_paragraphs(text, styles)
        story.extend(flowables)
        story.append(Spacer(1, 16))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully created PDF: {OUTPUT_PDF.resolve()} ({OUTPUT_PDF.stat().st_size} bytes)")


if __name__ == "__main__":
    build_pdf()
