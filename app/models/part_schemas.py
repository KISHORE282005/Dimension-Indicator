"""Schemas for the fixed-column part report workflow.

The Excel report always has the same ten columns in the same order, matching
the customer's reference sheet exactly. Everything in this module exists to
fill those columns for one or more parts while keeping full provenance (which
page, which source, how confident) for every value written.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# The fixed report contract - do not reorder or rename.
# Header text matches the reference sheet character for character.
# ---------------------------------------------------------------------------

REPORT_COLUMNS: tuple[str, ...] = (
    "S No",
    "PART NO",
    "DESCRIPTION",
    "DWG NO",
    "WEIGHT (IN KG)",
    "THICKNESS",
    "PROCESS",
    "LENGTH (mm)",
    "WIDTH (mm)",
    "HEIGHT (mm)",
)

#: Maps each report column to the internal field name used on PartInput.
COLUMN_TO_FIELD: dict[str, str] = {
    "S No": "s_no",
    "PART NO": "part_no",
    "DESCRIPTION": "description",
    "DWG NO": "dwg_no",
    "WEIGHT (IN KG)": "weight_kg",
    "THICKNESS": "thickness",
    "PROCESS": "process",
    "LENGTH (mm)": "length",
    "WIDTH (mm)": "width",
    "HEIGHT (mm)": "height",
}

FIELD_TO_COLUMN: dict[str, str] = {v: k for k, v in COLUMN_TO_FIELD.items()}

#: Columns whose values should be written to Excel as numbers when possible.
NUMERIC_COLUMNS: frozenset[str] = frozenset(
    {"WEIGHT (IN KG)", "THICKNESS", "LENGTH (mm)", "WIDTH (mm)", "HEIGHT (mm)"}
)

#: Columns already expressed in millimetres by their header, so a "mm" suffix
#: inside the cell would be redundant.
MM_COLUMNS: frozenset[str] = frozenset({"LENGTH (mm)", "WIDTH (mm)", "HEIGHT (mm)"})

#: Columns the drawing analysis may propose values for. S No is bookkeeping and
#: PART NO is the join key, so neither is ever inferred for an existing row.
EXTRACTABLE_FIELDS: tuple[str, ...] = (
    "description",
    "dwg_no",
    "weight_kg",
    "thickness",
    "process",
    "length",
    "width",
    "height",
)

NOT_DETECTED = "Not Detected"
NOT_AVAILABLE = "Not Available"

#: Values that mean "this field does not apply to this part" rather than
#: "we failed to find it". Bought-out parts legitimately have no thickness.
NOT_APPLICABLE_TOKENS: frozenset[str] = frozenset(
    {"na", "n/a", "n.a.", "not applicable", "-", "--"}
)


def is_not_applicable(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in NOT_APPLICABLE_TOKENS


class ValueSource(str, Enum):
    """Where the value written into a report cell came from."""

    USER = "user"
    DRAWING = "drawing"
    NOT_DETECTED = "not_detected"


class ValueStatus(str, Enum):
    """Relationship between the user's entry and the drawing."""

    USER_ONLY = "user_only"           # user supplied it, drawing silent
    CONFIRMED = "confirmed"           # user supplied it, drawing agrees
    CONFLICT = "conflict"             # user supplied it, drawing disagrees
    FILLED_FROM_DRAWING = "filled"    # user left blank, drawing supplied it
    MISSING = "missing"               # nobody supplied it
    USER_EDITED = "user_edited"       # user corrected it after analysis


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


class PartInput(BaseModel):
    """One row of user-supplied data, keyed by PART NO."""

    s_no: Optional[str] = None
    part_no: str = ""
    description: Optional[str] = None
    dwg_no: Optional[str] = None
    weight_kg: Optional[str] = None
    thickness: Optional[str] = None
    process: Optional[str] = None
    length: Optional[str] = None
    width: Optional[str] = None
    height: Optional[str] = None

    #: True when this row came from the drawing's BOM rather than the operator.
    discovered: bool = False

    def normalised_part_no(self) -> str:
        """Part number reduced for matching: uppercase, alphanumerics only."""
        return "".join(ch for ch in (self.part_no or "") if ch.isalnum()).upper()

    def user_value(self, field: str) -> Optional[str]:
        """The operator's entry for a field, or None if they left it blank.

        A discovered row carries drawing data, not operator data, so it never
        reports user values - otherwise BOM text would be treated as though a
        human had typed and confirmed it.
        """
        if self.discovered and field not in {"s_no", "part_no"}:
            return None
        raw = getattr(self, field, None)
        if raw is None:
            return None
        raw = str(raw).strip()
        return raw or None

    def has_any_value(self) -> bool:
        return any(
            (getattr(self, f, None) or "").strip()
            for f in ("part_no", *EXTRACTABLE_FIELDS)
        )


class AnalysisRequest(BaseModel):
    """Payload for POST /api/part-report/analyze.

    An empty `parts` list is valid and means "discover the parts from the
    drawing's BOM table".
    """

    document_id: str
    parts: list[PartInput] = Field(default_factory=list)
    use_vlm: bool = True
    use_ocr: bool = True


class CellEdit(BaseModel):
    """A single user correction to one report cell.

    Sent back after the operator edits a value (typically one that was shown
    red for "not detected") so the corrected value can be persisted and written
    green into the downloaded Excel file.
    """

    part_no: str
    column: str
    value: str

    def normalised_part_no(self) -> str:
        """Reduce PART NO for matching (uppercase, alphanumerics only)."""
        return "".join(ch for ch in (self.part_no or "") if ch.isalnum()).upper()


# ---------------------------------------------------------------------------
# Extraction output
# ---------------------------------------------------------------------------


class DiscoveredPart(BaseModel):
    """A part read out of the drawing's BOM / parts-list table."""

    part_no: str
    description: Optional[str] = None
    dwg_no: Optional[str] = None
    quantity: Optional[str] = None
    s_no: Optional[str] = None
    page_number: int = 0
    confidence: float = 0.0

    def normalised_part_no(self) -> str:
        return "".join(ch for ch in (self.part_no or "") if ch.isalnum()).upper()


class FieldEvidence(BaseModel):
    """A single value the drawing analysis proposed for one field of one part."""

    field: str
    value: str
    unit: Optional[str] = None
    page_number: int
    confidence: float = 0.0
    source_text: Optional[str] = None
    reasoning: Optional[str] = None


class ReportCell(BaseModel):
    """The resolved content of one cell, with its full provenance."""

    column: str
    value: str
    source: ValueSource = ValueSource.NOT_DETECTED
    status: ValueStatus = ValueStatus.MISSING
    confidence: float = 0.0
    page_references: list[int] = Field(default_factory=list)
    user_value: Optional[str] = None
    drawing_value: Optional[str] = None
    note: Optional[str] = None

    @property
    def is_conflict(self) -> bool:
        return self.status == ValueStatus.CONFLICT


class DrawingFinding(BaseModel):
    """A piece of technical information read off the drawing.

    These populate the "Extracted Drawing Information" panel. They are kept
    separate from report cells because most of what a drawing contains (GD&T,
    welds, holes, tolerances) has no home in the fixed columns but still needs
    to be shown and traced.
    """

    category: str
    value: str
    detail: Optional[str] = None
    page_number: int
    part_no: Optional[str] = None
    confidence: float = 0.0
    source: str = "vlm"


class PartReportRow(BaseModel):
    """One fully resolved row of the fixed-column report."""

    part_no: str
    cells: dict[str, ReportCell] = Field(default_factory=dict)
    findings: list[DrawingFinding] = Field(default_factory=list)
    matched_pages: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    discovered: bool = False

    def normalised_part_no(self) -> str:
        """Reduce PART NO for matching (uppercase, alphanumerics only)."""
        return "".join(ch for ch in (self.part_no or "") if ch.isalnum()).upper()

    def ordered_values(self) -> list[str]:
        return [
            self.cells[col].value if col in self.cells else NOT_AVAILABLE
            for col in REPORT_COLUMNS
        ]

    def to_flat_dict(self) -> dict[str, str]:
        return {
            col: self.cells[col].value if col in self.cells else NOT_AVAILABLE
            for col in REPORT_COLUMNS
        }


class PageAnalysis(BaseModel):
    """Per-page record, kept for traceability and the progress UI."""

    page_number: int
    ocr_text_length: int = 0
    ocr_regions: int = 0
    ocr_engine: str = "none"
    vlm_used: bool = False
    vlm_error: Optional[str] = None
    findings_count: int = 0
    parts_discovered: int = 0
    part_numbers_seen: list[str] = Field(default_factory=list)
    processing_time_seconds: float = 0.0


class PartReportResult(BaseModel):
    """Everything produced by one analysis run."""

    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str = ""
    filename: str = ""
    total_pages: int = 0
    pages_analyzed: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processing_time_seconds: float = 0.0

    rows: list[PartReportRow] = Field(default_factory=list)
    page_analyses: list[PageAnalysis] = Field(default_factory=list)
    unmatched_findings: list[DrawingFinding] = Field(default_factory=list)
    discovered_parts: list[DiscoveredPart] = Field(default_factory=list)

    #: True when the part rows came from the drawing's BOM rather than input.
    discovery_mode: bool = False

    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    ocr_engine: str = "none"
    vlm_model: str = "none"
    vlm_available: bool = False

    def conflict_count(self) -> int:
        return sum(
            1 for row in self.rows for cell in row.cells.values() if cell.is_conflict
        )

    def missing_count(self) -> int:
        return sum(
            1
            for row in self.rows
            for cell in row.cells.values()
            if cell.status == ValueStatus.MISSING
        )

    def apply_edits(self, edits: list["CellEdit"]) -> None:
        """Overwrite report cells with operator corrections.

        Each edit locates the row by PART NO and the cell by report column,
        stores the new value, and marks the cell as user-edited so it is drawn
        green in the table and in the Excel file. The original drawing value is
        preserved in ``drawing_value`` for the audit trail.
        """
        rows_by_part = {
            row.normalised_part_no(): row for row in self.rows
        }
        for edit in edits:
            row = rows_by_part.get(edit.normalised_part_no())
            if row is None:
                continue
            cell = row.cells.get(edit.column)
            if cell is None:
                cell = ReportCell(column=edit.column)
                row.cells[edit.column] = cell
            was_missing = cell.status == ValueStatus.MISSING
            if not cell.drawing_value and cell.source == ValueSource.DRAWING:
                cell.drawing_value = cell.value
            cell.value = edit.value.strip() or edit.value
            cell.source = ValueSource.USER
            cell.status = ValueStatus.USER_EDITED
            cell.user_value = cell.value
            if was_missing or cell.note is None:
                cell.note = (
                    "Corrected by the operator after analysis. "
                    "This value overrides what was detected on the drawing."
                )

    def filled_count(self) -> int:        return sum(
            1
            for row in self.rows
            for cell in row.cells.values()
            if cell.status == ValueStatus.FILLED_FROM_DRAWING
        )

    def table_payload(self) -> dict[str, Any]:
        """Shape consumed by the report preview table in the UI."""
        return {
            "columns": list(REPORT_COLUMNS),
            "rows": [
                {
                    "part_no": row.part_no,
                    "values": row.ordered_values(),
                    "cells": {c: row.cells[c].model_dump() for c in row.cells},
                    "warnings": row.warnings,
                    "discovered": row.discovered,
                }
                for row in self.rows
            ],
        }
