"""Automatic manufacturing-process detection from drawing text and findings.

The VLM may fail to name a process even when the drawing clearly shows one, so
this module scans the page's OCR text and symbol findings for tell-tale markers
and turns them into :class:`FieldEvidence` for the ``process`` field. It does
not guess from geometry - every process it reports is anchored to a marker the
user can see on the drawing:

* **bending** - a *bend radius* and/or *bend angle* (e.g. a ``BEND`` note,
  ``R=...`` on a bend line, a ``90°`` bend angle callout, a bend allowance).
* **welding** - a welding / fillet-weld symbol or a fillet-size callout such as
  ``z1``, ``z2``, ``a5``, ``Z6``, or the word ``welding`` / ``weld`` in a note.

Two other common in-house processes are recognised from their words as well:
``laser cutting`` and ``tapping``. ``drilling`` is inferred only from an
explicit drill/hole marker so ordinary punchings are not miscounted.

Only known processes are ever emitted and they are always joined with commas
in a stable order, matching the report's PROCESS column.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Optional

from app.models.part_schemas import FieldEvidence

logger = logging.getLogger(__name__)

#: Canonical process values this module may emit, in report order.
KNOWN_PROCESSES: tuple[str, ...] = (
    "laser cutting",
    "bending",
    "drilling",
    "tapping",
    "welding",
)


# ---------------------------------------------------------------------------
# Marker matchers. Each returns the exact marker text when the process is
# present in the OCR text, else None.
# ---------------------------------------------------------------------------


def detect_laser_cutting(text: str) -> Optional[str]:
    m = re.search(
        r"\blaser[\s-]*(?:cut|cutting)?\b|\blaser\b|\bplasma[\s-]*cut",
        text,
        re.IGNORECASE,
    )
    return m.group(0).strip() if m else None


def detect_drilling(text: str) -> Optional[str]:
    m = re.search(
        r"\bdrill(?:ing|ed)?\b|\bdrilled hole\b|\bdrill size\b",
        text,
        re.IGNORECASE,
    )
    return m.group(0).strip() if m else None


def detect_bending(text: str) -> Optional[str]:
    patterns = (
        # explicit bend keywords
        r"\bbending\b",
        r"\bbend(?:ing)?[\s-]*(?:radius|allowance|line|direction|angle)\b",
        r"\bbend\b",
        # bend-angle callout, e.g. "BEND 90 DEG" or "90° BEND"
        r"\bbend\s*\d+\s*(?:deg|°)\b",
        r"\bd\s+[-+]?\d*\s*(?:deg|°)\s*(?:bend|come)\b",
        r"\bbend radius (?:r|=)\s*[-+]?\d",
        r"\bbr\s*[-+]?\d+\b",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None


def detect_tapping(text: str) -> Optional[str]:
    m = re.search(
        r"\btap(?:ping|ped)?\b|\bthreaded\b|\btapped hole\b",
        text,
        re.IGNORECASE,
    )
    return m.group(0).strip() if m else None


def detect_welding(text: str) -> Optional[str]:
    patterns = (
        r"\bwelding\b",
        r"\bweld(?:s|ing|ed)?\b",
        r"\bfillet\b",
        r"\belectric weld\b",
        # fillet / weld size callout, e.g. "z1", "z2", "a5", "Z 6"
        r"\b[zaZA]\.?\s*\d+(?:\.\d+)?\b",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None


_DETECTORS: tuple[tuple[str, object], ...] = (
    ("laser cutting", detect_laser_cutting),
    ("bending", detect_bending),
    ("drilling", detect_drilling),
    ("tapping", detect_tapping),
    ("welding", detect_welding),
)


def detect_processes_from_text(text: str) -> list[str]:
    """Return the known processes found in ``text``, in stable order."""
    found: list[str] = []
    for process, func in _DETECTORS:
        if func(text):
            found.append(process)
    return found


def _normalise_part_no(value: Optional[str]) -> str:
    return "".join(ch for ch in (value or "") if ch.isalnum()).upper()


def process_evidence_for_parts(
    text: str,
    page_number: int,
    part_numbers: Iterable[str],
    confidence: float = 0.85,
) -> list[tuple[str, FieldEvidence]]:
    """Build ``process`` FieldEvidence records for the parts on this page.

    Only attributes the process to parts whose number the caller says are on
    this page. Returns a list of ``(part_no, FieldEvidence)`` pairs ready to be
    merged into the per-part evidence index.
    """
    processes = detect_processes_from_text(text or "")
    if not processes:
        return []

    parts = [p for p in part_numbers if _normalise_part_no(p)]
    if not parts:
        return []

    value = ", ".join(processes)
    marker_notes = []
    for process in processes:
        for detector_name, func in _DETECTORS:
            if detector_name == process:
                marker = func(text or "")
                if marker:
                    marker_notes.append(f"{process} (indicated by '{marker}')")
                break

    evidence: list[tuple[str, FieldEvidence]] = []
    for part_no in parts:
        evidence.append(
            (
                part_no,
                FieldEvidence(
                    field="process",
                    value=value,
                    page_number=page_number,
                    confidence=confidence,
                    source_text=value,
                    reasoning="; ".join(marker_notes)
                    or "Detected from manufacturing markers on the drawing",
                ),
            )
        )
    return evidence
