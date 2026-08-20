"""FastAPI backend — REST API for engineering drawing analysis."""

from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models.database import DatabaseManager
from app.models.schemas import DocumentAnalysisResult
from app.pipeline.orchestrator import PipelineOrchestrator
from app.backend.report_generator import ReportGenerator
from app.backend.part_routes import router as part_report_router
from app.backend.excel_report import ExcelReportWriter
from app.backend.legacy_adapter import build_report_from_analysis

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Based Engineering Drawing Analysis and Automated Report Generation",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"

db = DatabaseManager()
report_gen = ReportGenerator()

# The legacy orchestrator loads PaddleOCR weights on construction, which would
# add tens of seconds to server startup. Build it on first use instead.
_orchestrator: Optional[PipelineOrchestrator] = None


class _LazyOrchestrator:
    """Proxies attribute access to a PipelineOrchestrator built on demand."""

    def __getattr__(self, name: str):
        global _orchestrator
        if _orchestrator is None:
            _orchestrator = PipelineOrchestrator()
        return getattr(_orchestrator, name)


orchestrator = _LazyOrchestrator()

# The fixed-column part report workflow.
app.include_router(part_report_router)

# In-memory progress tracking
_progress: dict[str, dict] = {}


@app.get("/", include_in_schema=False)
async def index():
    """Serve the part report interface."""
    return FileResponse(str(_UI_DIR / "index.html"))


# ------------------------------------------------------------------
# Health & status
# ------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "ocr_available": orchestrator.ocr_engine.is_available(),
        "vlm_available": orchestrator.vlm_engine.is_available(),
    }


@app.get("/api/status")
async def system_status():
    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "ocr_engine": "PaddleOCR" if orchestrator.ocr_engine.is_available() else "unavailable",
        "vlm_engine": settings.GEMINI_MODEL if orchestrator.vlm_engine.is_available() else "unavailable",
        "rule_engine": "active",
        "database": "active",
    }


# ------------------------------------------------------------------
# File upload & analysis
# ------------------------------------------------------------------

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload an engineering drawing (PDF or image)."""
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = Path(file.filename).suffix.lower()
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported file type: {ext}. Allowed: {', '.join(allowed)}")

    doc_id = str(uuid.uuid4())
    save_path = settings.UPLOAD_DIR / f"{doc_id}{ext}"
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {
        "document_id": doc_id,
        "filename": file.filename,
        "file_path": str(save_path),
        "file_size": save_path.stat().st_size,
    }


@app.post("/api/analyze/{document_id}")
async def analyze_document(
    document_id: str,
    use_vlm: bool = Query(True, description="Use VLM reasoning layer"),
    ocr_min_confidence: float = Query(0.3, ge=0.0, le=1.0),
):
    """Run full analysis pipeline on an uploaded document."""
    # Find the uploaded file
    upload_files = list(settings.UPLOAD_DIR.glob(f"{document_id}.*"))
    if not upload_files:
        raise HTTPException(404, f"Document not found: {document_id}")

    file_path = upload_files[0]
    _progress[document_id] = {"stage": "starting", "progress": 0.0}

    def progress_callback(stage: str, pct: float):
        _progress[document_id] = {"stage": stage, "progress": pct}

    orchestrator.set_progress_callback(progress_callback)

    try:
        result = orchestrator.analyze(
            file_path=str(file_path),
            use_vlm=use_vlm,
            ocr_min_confidence=ocr_min_confidence,
        )
        db.save_analysis(result)
        _progress[document_id] = {"stage": "complete", "progress": 1.0}

        return {
            "document_id": result.document_id,
            "filename": result.filename,
            "total_pages": result.total_pages,
            "processing_time": result.total_processing_time_seconds,
            "summary": result.extraction_summary,
            "is_valid": result.validation_result.is_valid if result.validation_result else None,
            "issues_count": len(result.all_issues),
        }
    except Exception as e:
        logger.error("Analysis failed: %s", e)
        _progress[document_id] = {"stage": "error", "progress": 0.0, "error": str(e)}
        raise HTTPException(500, f"Analysis failed: {e}")


@app.get("/api/progress/{document_id}")
async def get_progress(document_id: str):
    """Get analysis progress for a document."""
    return _progress.get(document_id, {"stage": "unknown", "progress": 0.0})


# ------------------------------------------------------------------
# Results retrieval
# ------------------------------------------------------------------

@app.get("/api/results/{document_id}")
async def get_results(document_id: str):
    """Get full analysis results."""
    result = db.get_analysis(document_id)
    if not result:
        raise HTTPException(404, "Analysis not found")
    return result.model_dump()


@app.get("/api/results/{document_id}/summary")
async def get_summary(document_id: str):
    """Get extraction summary."""
    result = db.get_analysis(document_id)
    if not result:
        raise HTTPException(404, "Analysis not found")
    result.build_summary()
    return {
        "document_id": result.document_id,
        "filename": result.filename,
        "total_pages": result.total_pages,
        "summary": result.extraction_summary,
        "is_valid": result.validation_result.is_valid if result.validation_result else None,
        "processing_time": result.total_processing_time_seconds,
    }


@app.get("/api/results/{document_id}/page/{page_number}")
async def get_page_result(document_id: str, page_number: int):
    """Get results for a specific page."""
    result = db.get_analysis(document_id)
    if not result:
        raise HTTPException(404, "Analysis not found")
    for pr in result.page_results:
        if pr.page_number == page_number:
            return pr.model_dump()
    raise HTTPException(404, f"Page {page_number} not found")


@app.get("/api/results/{document_id}/items")
async def get_items(
    document_id: str,
    category: Optional[str] = Query(None),
    page: Optional[int] = Query(None),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
):
    """Get extracted items with optional filtering."""
    result = db.get_analysis(document_id)
    if not result:
        raise HTTPException(404, "Analysis not found")

    items = []
    for pr in result.page_results:
        all_items = (
            pr.dimensions + pr.tolerances + pr.holes + pr.welding_items
            + pr.gd_t_items + pr.datums + pr.surface_finishes + pr.materials
            + pr.manufacturing_notes + pr.bom_items + pr.section_views
            + pr.detail_views + pr.critical_characteristics
        )
        for item in all_items:
            if category and item.category.value != category:
                continue
            if page and item.page_number != page:
                continue
            if min_confidence and item.confidence < min_confidence:
                continue
            items.append(item.model_dump())
    return items


@app.get("/api/results/{document_id}/issues")
async def get_issues(document_id: str, severity: Optional[str] = Query(None)):
    """Get detected issues with optional severity filter."""
    result = db.get_analysis(document_id)
    if not result:
        raise HTTPException(404, "Analysis not found")

    issues = [i.model_dump() for i in result.all_issues]
    if severity:
        issues = [i for i in issues if i["severity"] == severity]
    return issues


@app.get("/api/results/{document_id}/validation")
async def get_validation(document_id: str):
    """Get validation result."""
    result = db.get_analysis(document_id)
    if not result:
        raise HTTPException(404, "Analysis not found")
    if not result.validation_result:
        return {"message": "Validation not performed"}
    return result.validation_result.model_dump()


@app.get("/api/results/{document_id}/json")
async def get_json_export(document_id: str):
    """Export full result as JSON."""
    result = db.get_analysis(document_id)
    if not result:
        raise HTTPException(404, "Analysis not found")
    return json.loads(result.model_dump_json())


# ------------------------------------------------------------------
# Report generation
# ------------------------------------------------------------------

@app.get("/api/results/{document_id}/dcl")
async def get_dimension_control_list(document_id: str):
    """Get the consolidated dimension control list."""
    result = db.get_analysis(document_id)
    if not result:
        raise HTTPException(404, "Analysis not found")
    result.build_consolidated_dimension_control()
    return [row.model_dump() for row in result.consolidated_dimension_control]


@app.get("/api/reports/{document_id}/pdf")
async def generate_pdf_report(document_id: str):
    """Generate and download PDF report."""
    result = db.get_analysis(document_id)
    if not result:
        raise HTTPException(404, "Analysis not found")
    try:
        pdf_path = report_gen.generate_pdf(result)
        return FileResponse(
            str(pdf_path),
            media_type="application/pdf",
            filename=f"engineering_report_{document_id[:8]}.pdf",
        )
    except Exception as e:
        raise HTTPException(500, f"PDF generation failed: {e}")


@app.get("/api/reports/{document_id}/excel")
async def generate_excel_report(document_id: str):
    """Generate and download Excel report."""
    result = db.get_analysis(document_id)
    if not result:
        raise HTTPException(404, "Analysis not found")
    # One Excel format across the whole application: the fixed nine columns.
    # This endpoint has no input form, so every column is either read from the
    # drawing or reported as "Not Detected".
    try:
        report = build_report_from_analysis(result)
        xlsx_path = ExcelReportWriter().generate(report)
        return FileResponse(
            str(xlsx_path),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=f"engineering_report_{document_id[:8]}.xlsx",
        )
    except Exception as e:
        logger.exception("Excel generation failed for %s", document_id)
        raise HTTPException(500, f"Excel generation failed: {e}")


# ------------------------------------------------------------------
# Page images
# ------------------------------------------------------------------

@app.get("/api/pages/{document_id}/{page_number}")
async def get_page_image(document_id: str, page_number: int):
    """Get a rendered page image."""
    upload_files = list(settings.UPLOAD_DIR.glob(f"{document_id}.*"))
    if not upload_files:
        raise HTTPException(404, "Document not found")

    try:
        import fitz
        doc = fitz.open(str(upload_files[0]))
        if page_number < 1 or page_number > len(doc):
            raise HTTPException(400, f"Invalid page number: {page_number}")

        page = doc[page_number - 1]
        zoom = settings.PDF_RENDER_DPI / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_path = settings.OUTPUT_DIR / f"{document_id}_page{page_number}.png"
        pix.save(str(img_path))
        doc.close()
        return FileResponse(str(img_path), media_type="image/png")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to render page: {e}")


# ------------------------------------------------------------------
# History
# ------------------------------------------------------------------

@app.get("/api/history")
async def list_history(limit: int = Query(50, ge=1, le=200)):
    """List previous analyses."""
    return db.list_analyses(limit=limit)


@app.delete("/api/history/{document_id}")
async def delete_analysis(document_id: str):
    """Delete an analysis from history."""
    if db.delete_analysis(document_id):
        return {"message": "Deleted"}
    raise HTTPException(404, "Analysis not found")


# ------------------------------------------------------------------
# Static UI (mounted last so it cannot shadow the API routes)
# ------------------------------------------------------------------

if _UI_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")
else:  # pragma: no cover - only if the checkout is incomplete
    logger.warning("UI directory missing: %s", _UI_DIR)
