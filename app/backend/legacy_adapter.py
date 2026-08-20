"""Adapts a legacy DocumentAnalysisResult into the fixed-column report.

The original pipeline (`/api/analyze/{id}`, used by the React UI) produces a
`DocumentAnalysisResult`: a flat catalogue of everything found on the drawing,
with no notion of user-supplied part rows. This module projects that catalogue
onto the same nine fixed columns the part report uses, so there is exactly one
Excel format in the application no matter which endpoint produced it.

There is no user input on this path, so every column is either read from the
drawing or reported as "Not Detected". Nothing is inferred to fill a gap.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from app.models.part_schemas import (
    NOT_DETECTED,
    REPORT_COLUMNS,
    DrawingFinding,
    PageAnalysis,
    PartReportResult,
    PartReportRow,
    ReportCell,
    ValueSource,
    ValueStatus,
)
from app.models.schemas import BOMItem, DocumentAnalysisResult, DrawingMetadata

logger = logging.getLogger(__name__)

#: Maps a legacy extraction category onto a findings category.
_CATEGORY_MAP = {
    "dimension": "dimension",
    "tolerance": "tolerance",
    "hole": "hole",
    "welding": "weld",
    "gd_t": "gdt",
    "datum": "datum",
    "surface_finish": "surface_finish",
    "material": "material",
    "manufacturing_note": "note",
    "bom": "bom",
    "section_view": "view",
    "detail_view": "view",
    "drawing_info": "title_block",
    "annotation": "other",
}

_WEIGHT_RE = re.compile(r"([-+]?\d+(?:[.,]\d+)?)\s*(kg|g|lb|t)?", re.IGNORECASE)

#: Columns the legacy BOM model simply does not carry.
_UNAVAILABLE_COLUMNS = (
    "THICKNESS", "PROCESS", "LENGTH (mm)", "WIDTH (mm)", "HEIGHT (mm)",
)


def _norm_part(value: Optional[str]) -> str:
    return "".join(ch for ch in (value or "") if ch.isalnum()).upper()


def _same_part(a: Optional[str], b: Optional[str]) -> bool:
    x, y = _norm_part(a), _norm_part(b)
    return bool(x and y and (x == y or x in y or y in x))


def _cell(
    column: str,
    value: Optional[str],
    page: Optional[int],
    confidence: float,
    note: str,
) -> ReportCell:
    """Build a cell that is either read from the drawing or Not Detected."""
    text = (value or "").strip()
    if not text:
        return ReportCell(
            column=column,
            value=NOT_DETECTED,
            source=ValueSource.NOT_DETECTED,
            status=ValueStatus.MISSING,
            confidence=0.0,
            note="Not found on the drawing. No value was supplied for this run.",
        )
    return ReportCell(
        column=column,
        value=text,
        source=ValueSource.DRAWING,
        status=ValueStatus.FILLED_FROM_DRAWING,
        confidence=confidence,
        page_references=[page] if page else [],
        drawing_value=text,
        note=note,
    )


def _normalise_weight(raw: Optional[str]) -> Optional[str]:
    """Return a kilogram figure only when the source unit is actually printed."""
    if not raw:
        return None
    match = _WEIGHT_RE.search(str(raw))
    if not match:
        return None
    number = float(match.group(1).replace(",", "."))
    unit = (match.group(2) or "").lower()
    factor = {"kg": 1.0, "g": 0.001, "lb": 0.45359237, "t": 1000.0}.get(unit)
    if factor is None:
        # No printed unit - do not guess that the number means kilograms.
        return str(raw).strip()
    return f"{number * factor:g} kg"


def build_report_from_analysis(result: DocumentAnalysisResult) -> PartReportResult:
    """Project a legacy analysis onto the fixed nine-column report."""
    report = PartReportResult(
        document_id=result.document_id,
        filename=result.filename,
        total_pages=result.total_pages,
        pages_analyzed=len(result.page_results),
        processing_time_seconds=result.total_processing_time_seconds or 0.0,
        vlm_available=True,
    )

    findings: list[DrawingFinding] = []
    bom_rows: list[tuple[BOMItem, int]] = []
    metadata: Optional[tuple[DrawingMetadata, int]] = None

    for page in result.page_results:
        report.page_analyses.append(
            PageAnalysis(
                page_number=page.page_number,
                vlm_used=bool(page.ai_interpretations),
                processing_time_seconds=page.processing_time_seconds or 0.0,
            )
        )

        if page.drawing_metadata is not None and metadata is None:
            metadata = (page.drawing_metadata, page.page_number)

        for item in page.bom_items:
            bom_rows.append((item, page.page_number))

        groups = (
            page.dimensions, page.tolerances, page.holes, page.welding_items,
            page.gd_t_items, page.datums, page.surface_finishes, page.materials,
            page.manufacturing_notes, page.bom_items, page.section_views,
            page.detail_views, page.critical_characteristics,
            page.other_annotations,
        )
        for group in groups:
            for item in group:
                value = str(getattr(item, "value", "") or "").strip()
                if not value:
                    continue
                raw_category = getattr(getattr(item, "category", None), "value", "other")
                findings.append(
                    DrawingFinding(
                        category=_CATEGORY_MAP.get(raw_category, "other"),
                        value=value,
                        detail=getattr(item, "source_text", None),
                        page_number=getattr(item, "page_number", page.page_number),
                        part_no=getattr(item, "part_number", None),
                        confidence=float(getattr(item, "confidence", 0.0) or 0.0),
                        source=str(
                            getattr(getattr(item, "source_type", None), "value", "vlm")
                        ),
                    )
                )

    for analysis in report.page_analyses:
        analysis.findings_count = sum(
            1 for f in findings if f.page_number == analysis.page_number
        )

    # One row per BOM part; otherwise a single row built from the title block.
    rows: list[PartReportRow] = []
    seen: set[str] = set()

    for item, page_number in bom_rows:
        part_no = (item.part_number or "").strip()
        if not part_no:
            continue
        key = _norm_part(part_no)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            _build_row(
                part_no=part_no,
                description=item.description,
                dwg_no=None,
                weight=_normalise_weight(item.weight),
                material=item.material,
                page_number=page_number,
                confidence=float(item.confidence or 0.0),
                index=len(rows) + 1,
            )
        )

    if not rows:
        meta, page_number = metadata if metadata else (None, None)
        rows.append(
            _build_row(
                part_no=meta.drawing_number if meta else None,
                description=meta.title if meta else None,
                dwg_no=meta.drawing_number if meta else None,
                weight=None,
                material=None,
                page_number=page_number,
                confidence=float(meta.confidence) if meta else 0.0,
                index=1,
            )
        )

    attributed: set[int] = set()
    for row in rows:
        for index, finding in enumerate(findings):
            if _same_part(finding.part_no, row.part_no):
                row.findings.append(finding)
                attributed.add(index)
        row.matched_pages = sorted({f.page_number for f in row.findings})

    report.rows = rows
    report.unmatched_findings = [
        f for i, f in enumerate(findings) if i not in attributed
    ]

    report.warnings.append(
        "This report came from the analysis-only endpoint, which has no input "
        "form, so every column was read from the drawing or marked "
        '"Not Detected". To supply S No, PART NO, WEIGHT, THICKNESS, PROCESS '
        "and the overall dimensions yourself, use the Part Report interface at "
        "the server root: http://localhost:8000/"
    )
    return report


def _build_row(
    part_no: Optional[str],
    description: Optional[str],
    dwg_no: Optional[str],
    weight: Optional[str],
    material: Optional[str],
    page_number: Optional[int],
    confidence: float,
    index: int,
) -> PartReportRow:
    label = (part_no or "").strip() or NOT_DETECTED
    row = PartReportRow(part_no=label)
    note = f"Read from page {page_number}" if page_number else ""

    row.cells["S No"] = ReportCell(
        column="S No",
        value=str(index),
        source=ValueSource.NOT_DETECTED,
        status=ValueStatus.FILLED_FROM_DRAWING,
        confidence=1.0,
        note="Auto-numbered by row order.",
    )
    row.cells["PART NO"] = _cell("PART NO", part_no, page_number, confidence, note)
    row.cells["DESCRIPTION"] = _cell(
        "DESCRIPTION", description, page_number, confidence, note
    )
    row.cells["DWG NO"] = _cell("DWG NO", dwg_no, page_number, confidence, note)
    row.cells["WEIGHT (IN KG)"] = _cell(
        "WEIGHT (IN KG)", weight, page_number, confidence, note
    )

    # The legacy BOM model carries none of these, so they are honestly reported
    # as absent rather than back-filled from an arbitrary dimension on the sheet.
    for column in _UNAVAILABLE_COLUMNS:
        row.cells[column] = _cell(column, None, None, 0.0, "")

    if material:
        row.warnings.append(f"Material read from the drawing: {material}")
    for column in REPORT_COLUMNS:
        if row.cells[column].status == ValueStatus.MISSING:
            row.warnings.append(f"{column}: not detected on the drawing.")
    return row
