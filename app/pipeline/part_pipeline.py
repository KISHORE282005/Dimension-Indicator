"""Orchestrates the fixed-column part report workflow.

Runs the complete document - every page, no early exit - and produces a
:class:`PartReportResult` ready for both the UI and the Excel writer.

If the operator supplied part rows, those define the report. If they did not,
the drawing's own parts-list table does, falling back to the title block when
the drawing has no such table - so assembly sheets, single detail drawings and
multi-sheet sets all work with no typing.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, Optional, Sequence

from app.config import settings
from app.engine.report_resolver import ReportResolver
from app.models.part_schemas import (
    DiscoveredPart,
    DrawingFinding,
    FieldEvidence,
    PageAnalysis,
    PartInput,
    PartReportResult,
)
from app.pipeline.document_processor import DocumentProcessor
from app.pipeline.ocr_engine import OCREngine
from app.pipeline.part_extractor import PartExtractor
from app.pipeline.symbol_detector import SymbolDetector

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, float, str], None]


class PartReportPipeline:
    """End-to-end pipeline: drawing + optional part rows -> fixed-column report."""

    def __init__(self) -> None:
        self.doc_processor = DocumentProcessor()
        self.ocr_engine = OCREngine()
        self.extractor = PartExtractor()
        self.resolver = ReportResolver()
        self.symbol_detector = SymbolDetector()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def capabilities(self) -> dict:
        return {
            "ocr_available": self.ocr_engine.is_available(),
            "ocr_engine": self.ocr_engine.engine_name,
            "ocr_note": self.ocr_engine.unavailable_reason,
            "vlm_available": self.extractor.is_available(),
            "vlm_model": settings.GEMINI_MODEL if self.extractor.is_available() else "none",
            "vlm_note": "" if self.extractor.is_available() else self.extractor.unavailable_reason,
            "symbol_detector_available": self.symbol_detector.is_available(),
            "symbol_detector_note": self.symbol_detector.status_note,
        }

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(
        self,
        file_path: str | Path,
        parts: Sequence[PartInput],
        document_id: str = "",
        use_vlm: bool = True,
        use_ocr: bool = True,
        ocr_min_confidence: float = 0.3,
        progress: Optional[ProgressCallback] = None,
    ) -> PartReportResult:
        file_path = Path(file_path)
        started = time.time()

        supplied = [p for p in parts if p.has_any_value()]
        discovery_mode = not supplied

        result = PartReportResult(
            document_id=document_id,
            filename=file_path.name,
            ocr_engine=self.ocr_engine.engine_name,
            vlm_model=settings.GEMINI_MODEL if self.extractor.is_available() else "none",
            vlm_available=self.extractor.is_available(),
            discovery_mode=discovery_mode,
        )

        def report(stage: str, pct: float, detail: str = "") -> None:
            if progress:
                progress(stage, pct, detail)
            logger.info("[%s] %.0f%% %s", stage, pct * 100, detail)

        if discovery_mode and not self.extractor.is_available():
            result.errors.append(
                "No part rows were entered and the vision model is unavailable, "
                "so there is nothing to build a report from. "
                + self.extractor.unavailable_reason
            )
            result.processing_time_seconds = time.time() - started
            return result

        # --- Stage 1: render every page --------------------------------
        report("rendering", 0.02, f"Opening {file_path.name}")
        try:
            pages = self.doc_processor.process_file(file_path)
        except Exception as e:
            logger.exception("Document processing failed")
            result.errors.append(f"Could not read the document: {e}")
            result.processing_time_seconds = time.time() - started
            return result

        result.total_pages = len(pages)
        if not pages:
            result.errors.append("The document contains no pages.")
            result.processing_time_seconds = time.time() - started
            return result

        report(
            "rendering", 0.10,
            f"{len(pages)} page(s) rendered at {settings.PDF_RENDER_DPI} DPI",
        )

        if use_vlm and not self.extractor.is_available():
            result.warnings.append(
                "Drawing analysis is disabled: " + self.extractor.unavailable_reason
            )
        if use_ocr and not self.ocr_engine.is_available():
            result.warnings.append(
                "PaddleOCR is not installed; using the PDF's own text layer instead. "
                "Scanned or image-only pages will yield no text. "
                + self.ocr_engine.unavailable_reason
            )

        # --- Stage 2: analyse each page --------------------------------
        evidence_by_part: dict[str, list[FieldEvidence]] = {}
        all_findings: list[DrawingFinding] = []
        discovered: dict[str, DiscoveredPart] = {}
        title_parts: dict[str, DiscoveredPart] = {}
        vlm_failures = 0

        # Pages get 10%..88% of the progress bar.
        span = 0.78
        for index, page in enumerate(pages):
            page_started = time.time()
            base = 0.10 + span * (index / len(pages))
            report(
                "analyzing", base,
                f"Page {page.page_number} of {len(pages)}: reading text",
            )

            analysis = PageAnalysis(page_number=page.page_number)

            ocr_results = []
            if use_ocr:
                if self.ocr_engine.is_available():
                    ocr_results = self.ocr_engine.extract_text(
                        page.processed_image,
                        page_number=page.page_number,
                        min_confidence=ocr_min_confidence,
                    )
                    analysis.ocr_engine = self.ocr_engine.engine_name
                if not ocr_results and page.text_blocks:
                    ocr_results = self.ocr_engine.results_from_text_blocks(
                        page.text_blocks, page.page_number
                    )
                    analysis.ocr_engine = "pdf-text-layer"

            ocr_text = self.ocr_engine.to_reading_order_text(ocr_results)
            analysis.ocr_regions = len(ocr_results)
            analysis.ocr_text_length = len(ocr_text)

            symbol_findings = self.symbol_detector.detect(page)
            all_findings.extend(symbol_findings)

            if use_vlm and self.extractor.is_available():
                report(
                    "analyzing",
                    base + span / len(pages) * 0.5,
                    f"Page {page.page_number} of {len(pages)}: interpreting drawing",
                )
                page_data = self.extractor.analyze_page(page, ocr_text, supplied)
                analysis.vlm_used = page_data.get("error") is None
                analysis.vlm_error = page_data.get("error")

                if page_data.get("error"):
                    vlm_failures += 1
                    result.warnings.append(
                        f"Page {page.page_number}: {page_data['error']}"
                    )

                for part_no, ev in page_data.get("evidence", []):
                    evidence_by_part.setdefault(part_no, []).append(ev)

                for part in page_data.get("bom_parts", []):
                    key = part.normalised_part_no()
                    # Keep the first sighting; later pages repeat the BOM.
                    if key and key not in discovered:
                        discovered[key] = part

                title = page_data.get("title_block")
                if title is not None:
                    key = title.normalised_part_no()
                    if key and key not in title_parts:
                        title_parts[key] = title

                page_findings = page_data.get("findings", [])
                all_findings.extend(page_findings)
                analysis.findings_count = len(page_findings) + len(symbol_findings)
                analysis.parts_discovered = len(page_data.get("bom_parts", []))
                analysis.part_numbers_seen = page_data.get("part_numbers", [])
            else:
                analysis.findings_count = len(symbol_findings)

            analysis.processing_time_seconds = time.time() - page_started
            result.page_analyses.append(analysis)
            result.pages_analyzed += 1

        if vlm_failures and vlm_failures == len(pages):
            result.errors.append(
                "Drawing analysis failed on every page. The report below contains "
                "only the values you entered."
            )

        result.discovered_parts = list(discovered.values())

        # --- Stage 3: decide the row set -------------------------------
        report("resolving", 0.90, "Building report rows")
        rows_input, note = self._select_rows(
            supplied, result.discovered_parts, list(title_parts.values())
        )
        if note:
            result.warnings.append(note)

        if not rows_input:
            result.errors.append(
                "No parts were entered, and neither a parts-list table nor a "
                "part number in the title block could be read from this "
                "drawing. Enter at least one PART NO and run the analysis again."
            )
            result.processing_time_seconds = time.time() - started
            report("complete", 1.0, "No rows to report")
            return result

        # --- Stage 4: resolve every cell -------------------------------
        report("resolving", 0.94, f"Resolving {len(rows_input)} part row(s)")
        rows, unmatched = self.resolver.resolve(
            rows_input, evidence_by_part, all_findings
        )
        for row, source in zip(rows, rows_input):
            row.discovered = source.discovered
        result.rows = rows
        result.unmatched_findings = unmatched

        if unmatched:
            result.warnings.append(
                f"{len(unmatched)} item(s) read from the drawing could not be "
                f"attributed to a specific part. They are listed separately and "
                f"are not in the report table."
            )

        conflicts = result.conflict_count()
        if conflicts:
            result.warnings.append(
                f"{conflicts} value(s) you entered disagree with the drawing. "
                f"Your values were kept; see the Traceability sheet."
            )

        result.processing_time_seconds = time.time() - started
        report(
            "complete", 1.0,
            f"{result.pages_analyzed} page(s), {len(rows)} part row(s) in "
            f"{result.processing_time_seconds:.1f}s",
        )
        return result

    # ------------------------------------------------------------------
    # Row selection
    # ------------------------------------------------------------------

    @staticmethod
    def _select_rows(
        supplied: Sequence[PartInput],
        discovered: Sequence[DiscoveredPart],
        title_parts: Sequence[DiscoveredPart] = (),
    ) -> tuple[list[PartInput], str]:
        """Choose the report's row set.

        Operator input always wins: if they typed rows, the drawing does not
        silently add or replace any of them. Otherwise the parts-list table is
        used, and failing that the title block - which is what identifies a
        single-part detail drawing or a set of detail sheets with no BOM.
        """
        if supplied:
            return list(supplied), ""

        source = discovered or title_parts
        if not source:
            return [], ""

        rows = [
            PartInput(
                s_no=part.s_no or str(index),
                part_no=part.part_no,
                description=part.description,
                dwg_no=part.dwg_no,
                discovered=True,
            )
            for index, part in enumerate(source, start=1)
        ]

        if discovered:
            origin = "the drawing's parts-list table"
        elif len(rows) == 1:
            origin = "the title block (this drawing shows a single part)"
        else:
            origin = "the title block of each sheet (no parts-list table found)"

        return rows, (
            f"No part rows were entered, so the {len(rows)} part(s) found in "
            f"{origin} were used. Every value comes from the drawing - check "
            f"them before relying on the report."
        )
