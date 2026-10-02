"""
reqtool.routers.exports
=======================
FastAPI router for export and traceability matrix endpoints.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Response

from reqtool.store import Store
from reqtool.models import ExportRequest, ExportMarkdownRequest, ExportCSVRequest
from reqtool.exports import (
    export_markdown_zip, export_csv, export_jsx,
    export_reqif_xml, export_coverage_matrix, export_gap_analysis,
    export_adr_markdown, export_pdf,
)
from .deps import get_store

log = logging.getLogger(__name__)

router = APIRouter(tags=["export"])


@router.get("/export/pdf")
def export_pdf_get_endpoint(product: str = None, store: Store = Depends(get_store)):
    """Export the complete repository specification as a PDF document."""
    pdf_bytes = export_pdf(store, product_id=product)
    filename = f"{store.config.repo_id or 'specification'}.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/export/pdf")
def export_pdf_post_endpoint(body: ExportRequest, store: Store = Depends(get_store)):
    """Export the complete repository specification as a PDF document."""
    pdf_bytes = export_pdf(store, product_id=body.product)
    filename = f"{store.config.repo_id or 'specification'}.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})



@router.get("/export/adr")
def export_adr_endpoint(store: Store = Depends(get_store)):
    """Export all Decision Records as standard Nygard-style ADR Markdown format."""
    md_content = export_adr_markdown(store)
    return Response(content=md_content.encode("utf-8"), media_type="text/markdown",
                    headers={"Content-Disposition": 'attachment; filename="architecture_decision_records.md"'})


@router.post("/export/jsx")
def export_jsx_endpoint(body: ExportRequest, store: Store = Depends(get_store)):
    content = export_jsx(store, body.product, body.variant)
    return Response(content=content, media_type="text/plain",
                    headers={"Content-Disposition": "attachment; filename=requirements.jsx"})


@router.post("/export/markdown")
def export_markdown_endpoint(body: ExportMarkdownRequest, store: Store = Depends(get_store)):
    content = export_markdown_zip(store, product_id=body.product,
                                   variant=body.variant, split_by=body.split_by)
    return Response(content=content, media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=requirements.zip"})


@router.post("/export/csv")
def export_csv_endpoint(body: ExportCSVRequest, store: Store = Depends(get_store)):
    content = export_csv(store, product_id=body.product,
                          variant=body.variant, fields=body.fields)
    return Response(content=content.encode("utf-8"), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=requirements.csv"})


@router.get("/export/reqif")
def export_reqif_endpoint(store: Store = Depends(get_store)):
    """Export requirements as an OMG ReqIF 1.2 XML document."""
    xml_content = export_reqif_xml(store)
    return Response(content=xml_content, media_type="application/xml",
                    headers={"Content-Disposition": 'attachment; filename="requirements.reqif"'})


@router.get("/traceability/matrix")
def get_coverage_matrix(
    source_type: str = "stakeholder_need",
    target_type: str = "functional",
    store: Store = Depends(get_store),
):
    """Return 2D coverage matrix mapping source_type requirements to target_type requirements."""
    return export_coverage_matrix(store, source_type=source_type, target_type=target_type)


@router.get("/traceability/gaps")
def get_gap_analysis(store: Store = Depends(get_store)):
    """Audit requirements lacking acceptance criteria, verification methods, or upstream links."""
    return export_gap_analysis(store)


from reqtool.intelligence import generate_audit_package

@router.get("/export/audit-package")
def export_audit_package(store: Store = Depends(get_store)):
    """Export 21 CFR Part 11 / ISO 26262 Regulatory Compliance Audit Package (Zip)."""
    zip_bytes = generate_audit_package(store)
    return Response(content=zip_bytes, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="regulatory_compliance_audit_package.zip"'})
