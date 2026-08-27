"""REST API for the fixed-column part report workflow.

Analysis of a multi-page drawing takes minutes, so it runs on a worker thread
and the client polls for progress. Jobs are held in memory; results are also
written to disk as JSON so a finished report survives a restart.
"""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from typing import List

from app.backend.excel_report import ExcelReportWriter
from app.config import settings
from app.models.part_schemas import (
    REPORT_COLUMNS,
    AnalysisRequest,
    PartInput,
    PartReportResult,
)
from app.pipeline.part_pipeline import PartReportPipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/part-report", tags=["part-report"])

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB
#: A single batch accepts up to this many drawings. A single drawing still
#: works - one is always allowed - but batches of 2..MAX_FILES_PER_BATCH are
#: combined into one report.
MAX_FILES_PER_BATCH = 15

_pipeline: Optional[PartReportPipeline] = None
_pipeline_lock = threading.Lock()

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="analysis")

_excel_writer = ExcelReportWriter()
RESULTS_DIR = Path(settings.OUTPUT_DIR) / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def get_pipeline() -> PartReportPipeline:
    """Build the pipeline once, on first use.

    Constructing it imports PaddleOCR and the Gemini SDK, which is slow enough
    that doing it at module import would stall server startup.
    """
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                _pipeline = PartReportPipeline()
    return _pipeline


# ---------------------------------------------------------------------------
# Job bookkeeping
# ---------------------------------------------------------------------------


def _set_job(job_id: str, **fields: Any) -> None:
    with _jobs_lock:
        _jobs.setdefault(job_id, {}).update(fields)


def _get_job(job_id: str) -> Optional[dict]:
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def _result_path(job_id: str) -> Path:
    return RESULTS_DIR / f"{job_id}.json"


def _load_result(job_id: str) -> Optional[PartReportResult]:
    """Fetch a finished result from memory, falling back to disk."""
    job = _get_job(job_id)
    if job and job.get("result") is not None:
        return job["result"]

    path = _result_path(job_id)
    if path.exists():
        try:
            return PartReportResult.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("Could not read cached result %s: %s", job_id, e)
    return None


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


@router.get("/capabilities")
async def capabilities() -> dict:
    """What the server can actually do right now.

    The UI uses this to warn up front rather than after a long analysis run.
    """
    caps = get_pipeline().capabilities()
    caps["report_columns"] = list(REPORT_COLUMNS)
    caps["pdf_render_dpi"] = settings.PDF_RENDER_DPI
    caps["max_upload_mb"] = MAX_UPLOAD_BYTES // (1024 * 1024)
    caps["ready"] = caps["vlm_available"]
    return caps


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload(files: List[UploadFile] = File(...)) -> dict:
    """Accept one or more drawings and combine them into a single set.

    One drawing (a PDF or an image) is a normal single-part batch. Ten to
    fifteen drawings uploaded together are combined into one multi-page
    document and analysed as one unit - the report covers every drawing in a
    single fixed-column table.
    """
    if not files:
        raise HTTPException(400, "No files provided.")

    if len(files) > MAX_FILES_PER_BATCH:
        raise HTTPException(
            400,
            f"Too many drawings. A batch accepts up to {MAX_FILES_PER_BATCH} "
            f"drawings; you uploaded {len(files)}.",
        )

    document_id = str(uuid.uuid4())
    folder = Path(settings.UPLOAD_DIR) / document_id
    folder.mkdir(parents=True, exist_ok=True)

    infos: list[dict] = []
    total_size = 0

    for index, file in enumerate(files, start=1):
        if not file.filename:
            raise HTTPException(400, f"No filename provided for file {index}.")

        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                400,
                f"Unsupported file type '{ext}' in '{file.filename}'. Allowed: "
                f"{', '.join(sorted(ALLOWED_EXTENSIONS))}",
            )

        safe_name = "".join(ch for ch in Path(file.filename).stem
                            if ch.isalnum() or ch in " _-") or "drawing"
        destination = folder / f"{index:02d}_{safe_name}{ext}"

        size = 0
        try:
            with open(destination, "wb") as out:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if total_size + size > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            413,
                            f"Batch exceeds the "
                            f"{MAX_UPLOAD_BYTES // (1024*1024)} MB limit.",
                        )
                    out.write(chunk)
        except HTTPException:
            destination.unlink(missing_ok=True)
            raise
        except Exception as e:
            destination.unlink(missing_ok=True)
            raise HTTPException(500, f"Could not save the upload: {e}")

        if size == 0:
            destination.unlink(missing_ok=True)
            raise HTTPException(400, f"'{file.filename}' is empty.")

        total_size += size
        infos.append(
            {
                "filename": file.filename,
                "size_bytes": size,
                "page_count": _count_pages(destination, ext),
                "stored_as": destination.name,
            }
        )

    # Combine every drawing into a single multi-page PDF so the pipeline runs
    # once and produces one report with sequential page numbers.
    combined = _combine_uploads(folder, document_id)
    combined_pages = _count_pages(combined, ".pdf")

    return {
        "document_id": document_id,
        "filename": (
            f"{infos[0]['filename']} +{len(infos) - 1} more"
            if len(infos) > 1
            else infos[0]["filename"]
        ),
        "size_bytes": total_size,
        "page_count": combined_pages,
        "file_count": len(infos),
        "total_pages": combined_pages,
        "files": infos,
        "stored_as": combined.name,
    }


def _count_pages(path: Path, ext: str) -> int:
    if ext != ".pdf":
        return 1
    try:
        import fitz

        with fitz.open(str(path)) as doc:
            return len(doc)
    except Exception as e:
        logger.warning("Could not count pages in %s: %s", path.name, e)
        return 0


def _combine_uploads(folder: Path, document_id: str) -> Path:
    """Concatenate a batch folder's drawings into one multi-page PDF.

    PDFs are appended page for page; images are placed onto their own pages.
    Returns the path of the combined document, named ``<id>.combined.pdf`` so
    the existing ``<id>.*`` globs pick it up for analysis and preview.
    """
    import fitz

    combined = Path(settings.UPLOAD_DIR) / f"{document_id}.combined.pdf"
    files = sorted(
        (f for f in folder.iterdir() if f.suffix.lower() in ALLOWED_EXTENSIONS),
        key=lambda f: f.name,
    )

    out = fitz.open()
    try:
        for f in files:
            if f.suffix.lower() == ".pdf":
                src = fitz.open(str(f))
                try:
                    out.insert_pdf(src)
                finally:
                    src.close()
            else:
                page = out.new_page()
                try:
                    page.insert_image(page.rect, filename=str(f))
                except Exception as e:
                    logger.warning("Could not embed image %s: %s", f.name, e)
                    continue
        out.save(str(combined))
    except Exception as e:
        logger.error("Combining drawings into %s failed: %s", combined.name, e)
        raise
    finally:
        out.close()
    return combined


def _batch_display_name(document_id: str) -> str:
    """A human-friendly name for a batch, for report downloads."""
    folder = Path(settings.UPLOAD_DIR) / document_id
    if folder.is_dir():
        files = sorted(
            (f for f in folder.iterdir() if f.suffix.lower() in ALLOWED_EXTENSIONS),
            key=lambda f: f.name,
        )
        if files:
            stem = Path(files[0]).stem
            extra = len(files) - 1
            return f"{stem} +{extra} more" if extra else stem
    return document_id


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


@router.post("/analyze")
async def analyze(request: AnalysisRequest) -> dict:
    """Start analysis. Returns a job_id to poll."""
    matches = list(Path(settings.UPLOAD_DIR).glob(f"{request.document_id}.*"))
    matches = [m for m in matches if m.suffix.lower() in ALLOWED_EXTENSIONS]
    if not matches:
        raise HTTPException(404, f"Document not found: {request.document_id}")

    parts = _validate_parts(request.parts)
    job_id = str(uuid.uuid4())

    _set_job(
        job_id,
        document_id=request.document_id,
        status="queued",
        stage="queued",
        progress=0.0,
        detail="Waiting for a worker",
        started_at=datetime.utcnow().isoformat(),
        result=None,
        error=None,
    )

    _executor.submit(
        _run_analysis, job_id, matches[0], parts, request.use_vlm, request.use_ocr
    )
    return {
        "job_id": job_id,
        "status": "queued",
        "parts": len(parts),
        "mode": "supplied" if parts else "discovery",
    }


def _validate_parts(parts: list[PartInput]) -> list[PartInput]:
    """Drop blank rows and reject input that would make attribution ambiguous.

    An empty result is allowed and meaningful: it puts the run into discovery
    mode, where the drawing's own parts-list table defines the report.
    """
    cleaned = [p for p in parts if p.has_any_value()]
    if not cleaned:
        return []

    missing = [i + 1 for i, p in enumerate(cleaned) if not p.user_value("part_no")]
    if missing:
        raise HTTPException(
            400,
            f"PART NO is required on any row you fill in - it is how drawing "
            f"information is matched to a row. Missing on row(s): "
            f"{', '.join(map(str, missing))}. Leave the grid completely empty "
            f"to read the parts list from the drawing instead.",
        )

    seen: dict[str, int] = {}
    for i, p in enumerate(cleaned, start=1):
        key = p.normalised_part_no()
        if key in seen:
            raise HTTPException(
                400,
                f"PART NO '{p.part_no}' appears on rows {seen[key]} and {i}. "
                f"Part numbers must be unique so drawing data is not mixed "
                f"between rows.",
            )
        seen[key] = i
    return cleaned


def _run_analysis(
    job_id: str,
    file_path: Path,
    parts: list[PartInput],
    use_vlm: bool,
    use_ocr: bool,
) -> None:
    """Worker body. Runs off the event loop."""

    def progress(stage: str, pct: float, detail: str = "") -> None:
        _set_job(job_id, status="running", stage=stage, progress=pct, detail=detail)

    _set_job(job_id, status="running", stage="starting", progress=0.0)

    try:
        job = _get_job(job_id) or {}
        result = get_pipeline().run(
            file_path=file_path,
            parts=parts,
            document_id=job.get("document_id", ""),
            use_vlm=use_vlm,
            use_ocr=use_ocr,
            progress=progress,
        )

        try:
            _result_path(job_id).write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.warning("Could not cache result %s to disk: %s", job_id, e)

        # Auto-generate Excel report so the user never has to click Download.
        excel_path = None
        try:
            excel_path = _excel_writer.generate(result)
            logger.info("Auto-generated Excel report for job %s: %s", job_id, excel_path)
        except Exception as e:
            logger.warning("Auto Excel generation failed for job %s: %s", job_id, e)

        _set_job(
            job_id,
            status="complete",
            stage="complete",
            progress=1.0,
            detail=f"{result.pages_analyzed} page(s) analysed",
            result=result,
            excel_path=str(excel_path) if excel_path else None,
            finished_at=datetime.utcnow().isoformat(),
        )
    except Exception as e:
        logger.exception("Analysis job %s failed", job_id)
        _set_job(
            job_id,
            status="error",
            stage="error",
            progress=0.0,
            detail=str(e),
            error=str(e),
            finished_at=datetime.utcnow().isoformat(),
        )


@router.get("/progress/{job_id}")
async def progress(job_id: str) -> dict:
    job = _get_job(job_id)
    if job is None:
        if _result_path(job_id).exists():
            return {"job_id": job_id, "status": "complete", "progress": 1.0,
                    "stage": "complete", "detail": "Loaded from cache",
                    "excel_path": None}
        raise HTTPException(404, f"Unknown job: {job_id}")

    return {
        "job_id": job_id,
        "status": job.get("status"),
        "stage": job.get("stage"),
        "progress": job.get("progress", 0.0),
        "detail": job.get("detail", ""),
        "error": job.get("error"),
        "excel_path": job.get("excel_path"),
    }


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@router.get("/result/{job_id}")
async def result(job_id: str) -> dict:
    report = _load_result(job_id)
    if report is None:
        job = _get_job(job_id)
        if job and job.get("status") in {"queued", "running"}:
            raise HTTPException(409, "Analysis is still running.")
        raise HTTPException(404, f"No result for job {job_id}.")

    return {
        "job_id": job_id,
        "document_id": report.document_id,
        "filename": report.filename,
        "total_pages": report.total_pages,
        "pages_analyzed": report.pages_analyzed,
        "processing_time_seconds": round(report.processing_time_seconds, 2),
        "ocr_engine": report.ocr_engine,
        "vlm_model": report.vlm_model,
        "vlm_available": report.vlm_available,
        "discovery_mode": report.discovery_mode,
        "discovered_parts": [p.model_dump() for p in report.discovered_parts],
        "table": report.table_payload(),
        "findings": [
            {**f.model_dump(), "attributed_to": row.part_no}
            for row in report.rows
            for f in row.findings
        ],
        "unmatched_findings": [f.model_dump() for f in report.unmatched_findings],
        "page_analyses": [p.model_dump() for p in report.page_analyses],
        "warnings": report.warnings,
        "errors": report.errors,
        "row_warnings": {row.part_no: row.warnings for row in report.rows},
        "stats": {
            "conflicts": report.conflict_count(),
            "filled_from_drawing": report.filled_count(),
            "not_detected": report.missing_count(),
        },
    }


@router.get("/excel/{job_id}")
async def excel(job_id: str) -> FileResponse:
    """Generate and return the .xlsx report."""
    report = _load_result(job_id)
    if report is None:
        job = _get_job(job_id)
        if job and job.get("status") in {"queued", "running"}:
            raise HTTPException(409, "Analysis is still running.")
        raise HTTPException(404, f"No result for job {job_id}.")

    try:
        path = _excel_writer.generate(report)
    except Exception as e:
        logger.exception("Excel generation failed for job %s", job_id)
        raise HTTPException(500, f"Excel generation failed: {e}")

    stem = _batch_display_name(report.document_id)
    safe_stem = "".join(c for c in stem if c.isalnum() or c in "-_ ").strip() or "drawing"
    download_name = f"{safe_stem}_analysis_report.xlsx"

    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=download_name,
    )


@router.get("/page-image/{document_id}/{page_number}")
async def page_image(document_id: str, page_number: int) -> FileResponse:
    """Render one page as a PNG for the UI preview."""
    matches = list(Path(settings.UPLOAD_DIR).glob(f"{document_id}.*"))
    matches = [m for m in matches if m.suffix.lower() in ALLOWED_EXTENSIONS]
    if not matches:
        raise HTTPException(404, "Document not found.")

    source = matches[0]
    if source.suffix.lower() != ".pdf":
        return FileResponse(str(source))

    cache = Path(settings.OUTPUT_DIR) / f"{document_id}_p{page_number}.png"
    if cache.exists():
        return FileResponse(str(cache), media_type="image/png")

    try:
        import fitz

        with fitz.open(str(source)) as doc:
            if page_number < 1 or page_number > len(doc):
                raise HTTPException(404, f"Page {page_number} does not exist.")
            # 110 DPI is enough for an on-screen thumbnail.
            pixmap = doc[page_number - 1].get_pixmap(
                matrix=fitz.Matrix(110 / 72, 110 / 72), alpha=False
            )
            pixmap.save(str(cache))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Could not render page {page_number}: {e}")

    return FileResponse(str(cache), media_type="image/png")


@router.delete("/job/{job_id}")
async def delete_job(job_id: str) -> dict:
    with _jobs_lock:
        existed = _jobs.pop(job_id, None) is not None
    path = _result_path(job_id)
    if path.exists():
        path.unlink()
        existed = True
    if not existed:
        raise HTTPException(404, f"Unknown job: {job_id}")
    return {"deleted": job_id}
