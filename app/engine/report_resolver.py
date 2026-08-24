"""Resolves user input plus drawing evidence into the fixed report columns.

Policy, fixed by design:

* A value the user typed is ALWAYS what lands in the report cell. The drawing
  never silently overwrites an operator's entry.
* A blank cell may be filled from the drawing, but only when the evidence
  clears the confidence threshold. Otherwise it reads "Not Detected".
* Disagreement between the two is never hidden. It is recorded on the cell,
  raised as a row warning, and written to the Traceability sheet.

Every decision here is reversible from the recorded provenance: the cell keeps
both the user value and the drawing value along with page references.
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Sequence

from app.config import settings
from app.models.part_schemas import (
    COLUMN_TO_FIELD,
    MM_COLUMNS,
    NOT_AVAILABLE,
    NOT_DETECTED,
    REPORT_COLUMNS,
    DrawingFinding,
    FieldEvidence,
    PartInput,
    PartReportRow,
    ReportCell,
    ValueSource,
    ValueStatus,
)

logger = logging.getLogger(__name__)

_NUMBER_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")

#: Tolerance for treating two numeric values as the same measurement.
#: 1% relative catches unit-rounding (6 vs 6.0 vs 5.98) without masking a real
#: disagreement like 6 vs 8.
NUMERIC_REL_TOLERANCE = 0.01


class ReportResolver:
    """Turns user input and per-page evidence into finished report rows."""

    def __init__(self, confidence_threshold: Optional[float] = None) -> None:
        self.confidence_threshold = (
            settings.DIMENSION_CONFIDENCE_THRESHOLD
            if confidence_threshold is None
            else confidence_threshold
        )

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def resolve(
        self,
        parts: Sequence[PartInput],
        evidence_by_part: dict[str, list[FieldEvidence]],
        findings: Sequence[DrawingFinding],
    ) -> tuple[list[PartReportRow], list[DrawingFinding]]:
        """Build one row per supplied part.

        Returns the rows and any findings that could not be attributed to a
        part, which the UI shows in a separate "unattributed" section.
        """
        rows: list[PartReportRow] = []
        attributed: set[int] = set()

        # Index evidence by normalised part number. The drawing may print
        # "CP2071" where the row key is "CP-2071" - matching on the raw string
        # would silently drop every field found for that part.
        evidence_index: dict[str, list[FieldEvidence]] = {}
        for raw_key, items in evidence_by_part.items():
            evidence_index.setdefault(self._norm(raw_key), []).extend(items)

        for index, part in enumerate(parts, start=1):
            part_evidence = evidence_index.get(part.normalised_part_no(), [])
            row = self._resolve_row(part, index, part_evidence)

            for i, finding in enumerate(findings):
                if self._finding_belongs_to(finding, part):
                    row.findings.append(finding)
                    attributed.add(i)

            row.matched_pages = sorted(
                {e.page_number for e in part_evidence}
                | {f.page_number for f in row.findings}
            )
            if not row.matched_pages:
                row.warnings.append(
                    f"No information for Part No '{part.part_no}' was found on any "
                    f"page of this drawing."
                )
            rows.append(row)

        unmatched = [f for i, f in enumerate(findings) if i not in attributed]
        return rows, unmatched

    # ------------------------------------------------------------------
    # Row resolution
    # ------------------------------------------------------------------

    def _resolve_row(
        self, part: PartInput, index: int, evidence: Sequence[FieldEvidence]
    ) -> PartReportRow:
        row = PartReportRow(part_no=part.part_no or f"(row {index})")

        by_field: dict[str, list[FieldEvidence]] = {}
        for ev in evidence:
            by_field.setdefault(ev.field, []).append(ev)

        for column in REPORT_COLUMNS:
            field = COLUMN_TO_FIELD[column]

            if field == "s_no":
                row.cells[column] = self._resolve_s_no(part, index, column)
                continue
            if field == "part_no":
                row.cells[column] = self._resolve_part_no(part, column)
                continue

            cell = self._resolve_field(column, field, part, by_field.get(field, []))
            row.cells[column] = cell

            if cell.status == ValueStatus.CONFLICT:
                pages = ", ".join(str(p) for p in cell.page_references) or "?"
                row.warnings.append(
                    f"{column}: you entered '{cell.user_value}' but the drawing "
                    f"shows '{cell.drawing_value}' (page {pages}). "
                    f"Your value was kept."
                )
            elif cell.status == ValueStatus.MISSING:
                row.warnings.append(
                    f"{column}: not supplied and not detected on the drawing."
                )

        return row

    @staticmethod
    def _resolve_s_no(part: PartInput, index: int, column: str) -> ReportCell:
        supplied = part.user_value("s_no")
        return ReportCell(
            column=column,
            value=supplied or str(index),
            source=ValueSource.USER if supplied else ValueSource.NOT_DETECTED,
            status=ValueStatus.USER_ONLY if supplied else ValueStatus.FILLED_FROM_DRAWING,
            confidence=1.0,
            user_value=supplied,
            note=None if supplied else "Auto-numbered by row order.",
        )

    @staticmethod
    def _resolve_part_no(part: PartInput, column: str) -> ReportCell:
        supplied = part.user_value("part_no")
        return ReportCell(
            column=column,
            value=supplied or NOT_AVAILABLE,
            source=ValueSource.USER if supplied else ValueSource.NOT_DETECTED,
            status=ValueStatus.USER_ONLY if supplied else ValueStatus.MISSING,
            confidence=1.0 if supplied else 0.0,
            user_value=supplied,
        )

    def _resolve_field(
        self,
        column: str,
        field: str,
        part: PartInput,
        evidence: list[FieldEvidence],
    ) -> ReportCell:
        user_value = part.user_value(field)
        best = self._best_evidence(evidence)

        pages = sorted({e.page_number for e in evidence})
        drawing_value = self._format_evidence(best, column) if best else None

        # --- user supplied a value -------------------------------------
        if user_value:
            cell = ReportCell(
                column=column,
                value=user_value,
                source=ValueSource.USER,
                status=ValueStatus.USER_ONLY,
                confidence=1.0,
                page_references=pages,
                user_value=user_value,
                drawing_value=drawing_value,
            )
            if best is None:
                cell.note = "Not found on the drawing; your value was kept as entered."
                return cell

            if self._values_agree(user_value, drawing_value or ""):
                cell.status = ValueStatus.CONFIRMED
                cell.confidence = best.confidence
                cell.note = (
                    f"Confirmed on page {best.page_number}"
                    + (f": \"{best.source_text}\"" if best.source_text else "")
                )
            else:
                cell.status = ValueStatus.CONFLICT
                cell.confidence = best.confidence
                cell.note = (
                    f"Drawing page {best.page_number} shows '{drawing_value}'"
                    + (f" (\"{best.source_text}\")" if best.source_text else "")
                    + ". Your value was kept."
                )
            return cell

        # --- user left it blank ----------------------------------------
        if best is None:
            return ReportCell(
                column=column,
                value=NOT_DETECTED,
                source=ValueSource.NOT_DETECTED,
                status=ValueStatus.MISSING,
                confidence=0.0,
                note="Not supplied and not found on the drawing.",
            )

        if best.confidence < self.confidence_threshold:
            return ReportCell(
                column=column,
                value=NOT_DETECTED,
                source=ValueSource.NOT_DETECTED,
                status=ValueStatus.MISSING,
                confidence=best.confidence,
                page_references=pages,
                drawing_value=drawing_value,
                note=(
                    f"A possible value '{drawing_value}' was seen on page "
                    f"{best.page_number} but could not be read clearly enough "
                    f"to use (below the {self.confidence_threshold:.0%} "
                    f"acceptance cut-off). Not used."
                ),
            )

        return ReportCell(
            column=column,
            value=drawing_value or NOT_DETECTED,
            source=ValueSource.DRAWING,
            status=ValueStatus.FILLED_FROM_DRAWING,
            confidence=best.confidence,
            page_references=pages,
            drawing_value=drawing_value,
            note=(
                f"Read from page {best.page_number}"
                + (f": \"{best.source_text}\"" if best.source_text else "")
            ),
        )

    # ------------------------------------------------------------------
    # Evidence handling
    # ------------------------------------------------------------------

    def _best_evidence(
        self, evidence: Sequence[FieldEvidence]
    ) -> Optional[FieldEvidence]:
        """Pick the strongest evidence, rewarding agreement across pages.

        A value the drawing states on three pages is more trustworthy than a
        marginally more confident one-off, so agreeing readings reinforce each
        other before the maximum is taken.
        """
        if not evidence:
            return None
        if len(evidence) == 1:
            return evidence[0]

        scored: list[tuple[float, FieldEvidence]] = []
        for ev in evidence:
            agreeing = sum(
                1
                for other in evidence
                if other is not ev and self._values_agree(ev.value, other.value)
            )
            # Cap the bonus so corroboration cannot promote a low-confidence
            # reading past the threshold on its own.
            score = min(ev.confidence + 0.05 * agreeing, 0.99)
            scored.append((score, ev))

        scored.sort(key=lambda pair: (pair[0], -pair[1].page_number), reverse=True)
        return scored[0][1]

    @staticmethod
    def _format_evidence(evidence: FieldEvidence, column: str = "") -> str:
        value = (evidence.value or "").strip()
        unit = (evidence.unit or "").strip()
        if not unit or unit.lower() in {"null", "none"}:
            return value
        # The header already states the unit for these columns, so repeating it
        # in the cell is noise - and it would block numeric formatting.
        if column in MM_COLUMNS and unit.lower() in {"mm", "millimetre", "millimeter"}:
            return value
        if column == "WEIGHT (IN KG)" and unit.lower() in {"kg", "kgf", "kgs"}:
            return value
        # Do not double-print a unit the model already put in the value.
        if unit.lower() in value.lower():
            return value
        return f"{value} {unit}"

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    @classmethod
    def _values_agree(cls, a: str, b: str) -> bool:
        """Compare two field values tolerantly enough to avoid false conflicts."""
        a_norm = cls._normalise_text(a)
        b_norm = cls._normalise_text(b)
        if not a_norm or not b_norm:
            return False
        if a_norm == b_norm:
            return True

        a_num = cls._leading_number(a)
        b_num = cls._leading_number(b)
        if a_num is not None and b_num is not None:
            if a_num == b_num:
                return True
            scale = max(abs(a_num), abs(b_num))
            if scale == 0:
                return True
            return abs(a_num - b_num) / scale <= NUMERIC_REL_TOLERANCE

        # Textual fields (description, process): accept containment, which
        # covers "Laser Cutting" vs "Laser Cut".
        if a_num is None and b_num is None:
            if a_norm in b_norm or b_norm in a_norm:
                return True
        return False

    @staticmethod
    def _normalise_text(value: str) -> str:
        return re.sub(r"[^a-z0-9.]+", "", (value or "").lower())

    @staticmethod
    def _leading_number(value: str) -> Optional[float]:
        match = _NUMBER_RE.search(value or "")
        if not match:
            return None
        try:
            return float(match.group(0).replace(",", "."))
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # Finding attribution
    # ------------------------------------------------------------------

    @staticmethod
    def _norm(value: Optional[str]) -> str:
        return "".join(ch for ch in (value or "") if ch.isalnum()).upper()

    @staticmethod
    def _finding_belongs_to(finding: DrawingFinding, part: PartInput) -> bool:
        if not finding.part_no or not part.part_no:
            return False
        norm = lambda s: "".join(ch for ch in s if ch.isalnum()).upper()
        a, b = norm(finding.part_no), part.normalised_part_no()
        return bool(a and b and (a == b or a in b or b in a))
