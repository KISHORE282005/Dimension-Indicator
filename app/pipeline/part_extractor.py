"""Per-page drawing extraction mapped onto part rows.

The pipeline for one document is:

    for each page:
        render (clean)  ->  OCR (reading order)  ->  VLM  ->  evidence
    resolve evidence across all pages  ->  fixed-column report rows

Two modes:

* **Supplied mode** - the operator typed part rows. Evidence is attributed to
  those rows by PART NO and their typed values always win.
* **Discovery mode** - the grid was left empty. The drawing's own parts-list
  table becomes the row set, or the title block when there is no such table, so
  an assembly sheet or a single detail drawing both work with no typing.

Every value the model proposes is kept as :class:`FieldEvidence` carrying the
page it came from, a confidence, and the literal text on the drawing that
supports it. Nothing reaches the report without that provenance, which is what
makes "Not Detected" an honest answer rather than a fallback.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional, Sequence

from app.models.part_schemas import (
    EXTRACTABLE_FIELDS,
    FIELD_TO_COLUMN,
    DiscoveredPart,
    DrawingFinding,
    FieldEvidence,
    PartInput,
)
from app.pipeline.document_processor import ProcessedPage
from app.pipeline.gemini_client import GeminiClient, GeminiUnavailable

logger = logging.getLogger(__name__)

#: Readings that come from a sheet-metal DEVELOPMENT view (flat pattern /
#: unfolded blank) describe the blank before bending, never the finished part,
#: so they must not fill the LENGTH / WIDTH / HEIGHT columns.
_DEVELOPMENT_VIEW_RE = re.compile(
    r"\b(?:"
    r"develop(?:ed|ment|ments)?|dev\.?|"
    r"flat[\s-]*pattern(?:[\s-]*view)?|"
    r"unfold(?:ed|ing)?|"
    r"blank[\s-]*(?:size|length|dimension)|"
    r"stretch[\s-]*out"
    r")\b",
    re.IGNORECASE,
)

_LENGTH_FIELDS = frozenset({"length", "width", "height"})


FIELD_GUIDANCE = """\
Report the drawing's own wording and units. The examples below show the SHAPE of
what to look for, not a list to choose from - if the drawing says something the
examples do not mention, report what the drawing says.

- description: the part name as printed - the BOM description column, or the
  title block TITLE / DESCRIPTION / NOMENCLATURE / PART NAME field. Preserve the
  exact style, whether it is spaced words, underscores, hyphens or mixed case.
- dwg_no: the drawing/document number for THAT PART. When a parts-list table has
  a drawing-number column, use that row's value - one per part. It is NOT the
  sheet's own number in the title block, unless the page shows a single part and
  no per-part number exists. Column headings vary: DRAWING NUMBER, DWG NO,
  DOC NO, PART DRG, REF DRG.
- weight_kg: mass in kilograms. Convert only when the source unit is explicitly
  printed (g, kg, kgf, lb, oz, t). If a number is printed with no unit at all,
  report it as printed and do not assume a unit. On an assembly sheet the title
  block weight is the ASSEMBLY's weight - do not attribute it to a component.
- thickness: material or plate thickness - "6 THK", "t=6", "THK 8", "6mm PLATE",
  a gauge, or the stock size. When the drawing shows the part is purchased,
  standard or otherwise has no plate thickness, report the value "NA". Do NOT
  use an arbitrary small linear dimension as thickness.
- process: how the part is made, as the drawing states it. It may appear in the
  title block process/material field, a process or routing note, a BOM column,
  or a stamp. Examples of the kind of value expected: laser cutting, bending,
  machining, turning, milling, casting, forging, stamping, welding,
  fabrication, sheet metal, plasma/flame cutting, extrusion, moulding, or
  "bought out" / "purchased" / "standard part" for an item that is not made in
  house. Report whatever the drawing actually says, in its own words. Do NOT
  infer a process from the shape of the part.
- length / width / height: the overall bounding size of the FINISHED part,
  reported in MILLIMETRES. Convert only when the source unit is explicitly
  printed or stated by a units note (in/", ft, cm, m); put the converted number
  in `value`, "mm" in `unit`, and the original text in `source_text`. If the
  drawing states no unit anywhere, report the number as printed and leave
  `unit` null rather than assuming. Prefer an explicit overall/OA/envelope
  dimension or a stock size callout such as 200 x 100 x 6. Do NOT report a
  feature dimension (hole spacing, fillet, chamfer, bolt circle, thread size)
  as an overall dimension. Three hard orientation rules:
  * NEVER take a dimension from a DEVELOPMENT VIEW, FLAT PATTERN or UNFOLDED
    BLANK view. A development shows the stretched-out blank before bending -
    its length is longer than the finished part and must never be reported as
    length, width or height. Skip that view completely and read the finished
    part's orthographic views instead.
  * WIDTH IS OPPOSITE THE LENGTH: read LENGTH and WIDTH as a pair from ONE
    view. WIDTH is the measurement perpendicular to (across, not along) the
    LENGTH in that same view. Never take WIDTH from a different view or a
    different direction than LENGTH, and never use the plate thickness as
    WIDTH.
  * HEIGHT comes only from a 3D MODEL view (isometric / pictorial): HEIGHT is
    that model's Z axis - its vertical extent. If the page shows no 3D model
    view, omit height entirely; do NOT guess it from a plan or front view.
- thickness follows the same unit rule: convert to millimetres when the source
  unit is printed, and keep the original text in `source_text`.
"""

PAGE_PROMPT = """\
You are a senior manufacturing engineer reading one page of an engineering
drawing. Extract only what is genuinely visible on this page.

## Absolute rules

1. NEVER invent, guess, estimate, infer or round an engineering value. If a
   value is not printed on this page, omit that field entirely.
2. Do not carry knowledge from typical parts. Only this page counts.
3. If text is ambiguous or partly illegible, still omit the field rather than
   report a best guess. Note the ambiguity in `notes` instead.
4. Every field you report MUST include `source_text`: the exact characters you
   read on the drawing that justify the value. If you cannot quote it, omit it.
5. `confidence` must reflect how certain you are that you read this correctly
   AND that it belongs to this part. Use below 0.5 when unsure.
6. Report numbers without unit suffixes in `value`; put the unit in `unit`.

## The parts list, if this page has one

Many drawings carry a parts-list table. It may be titled PARTS LIST, BILL OF
MATERIALS, BOM, ITEM LIST, COMPONENT LIST or nothing at all, and it may sit in
any corner of the sheet. Its columns vary widely - some combination of item or
serial number (S.NO, SL, ITEM, POS, NO), part number (PART NO, PART NUMBER,
PART CODE, MATERIAL NO), description, drawing number, quantity, material,
weight and remarks. Match on meaning, not on exact column headings.

If such a table exists, read EVERY row into `bom_parts`, in table order. Do not
stop early, do not summarise, and do not skip rows that look repetitive - if
the table has forty rows, return forty entries. Where a table has no drawing
number or no description column, leave those fields null rather than inventing
them.

If this page has NO parts-list table - a single detail part, a general
arrangement, a schematic, a notes sheet - return `bom_parts` as an empty list.
That is a normal answer, not a failure. Fill in `title_block` instead, which is
what identifies a single-part drawing.

{parts_block}

## Fields to look for

{field_guidance}

## Text recognised on this page

The following text was extracted from this page in reading order. Use it to
read small text accurately, but trust the image where the two disagree.

```
{ocr_text}
```

## Output

Return ONLY this JSON object:

{{
  "page_summary": "one sentence on what this page shows",
  "page_type": "detail|assembly|bom|revision|notes|title|other",
  "bom_parts": [
    {{
      "s_no": "row number as printed",
      "part_no": "part number as printed",
      "description": "description as printed",
      "dwg_no": "drawing number for this part, or null",
      "quantity": "qty as printed, or null",
      "confidence": 0.0
    }}
  ],
  "title_block": {{
    "part_no": "the part number this SHEET is for, or null",
    "description": "the title of this sheet, or null",
    "dwg_no": "this sheet's own drawing number, or null",
    "confidence": 0.0
  }},
  "parts_on_page": [
    {{
      "part_no": "the part number this data belongs to",
      "matched_user_part_no": "exact part no from the supplied list, or null",
      "match_confidence": 0.0,
      "fields": {{
        "description": {{"value": "", "unit": null, "confidence": 0.0,
                          "source_text": "", "reasoning": ""}}
      }}
    }}
  ],
  "findings": [
    {{
      "category": "dimension|tolerance|hole|weld|gdt|datum|surface_finish|material|note|bom|view|title_block|revision|other",
      "value": "the callout exactly as printed",
      "detail": "what it means in one short phrase",
      "part_no": "part this belongs to, or null",
      "confidence": 0.0
    }}
  ],
  "notes": "anything illegible, ambiguous or contradictory on this page"
}}

`bom_parts` is empty only if this page genuinely has no parts-list table.
Include in `fields` ONLY the keys you actually found; an empty `fields` object
is valid and expected for pages that carry no per-part data.
Include EVERY dimension, tolerance, hole callout, weld symbol, GD&T frame,
surface finish symbol, datum, material spec, manufacturing note, section view
and detail view you can see in `findings`.
"""

_SUPPLIED_BLOCK = """\
## The parts this report is about

{rows}

Associate what you read with one of these part numbers. Part numbers on a
drawing may differ in punctuation or case (BR-1042 / BR1042 / br 1042) - treat
those as the same part. If information on this page clearly belongs to a
different part than any listed, set `part_no` to what the drawing shows and set
`matched_user_part_no` to null. If a page shows only one part and only one part
was supplied, you may associate them.

Values already supplied are shown so you can confirm or contradict them. Report
what the DRAWING says, even when it disagrees with the value above. Never echo
a supplied value back unless you can also read it on this page.
"""

_DISCOVERY_BLOCK = """\
## No parts were supplied

The parts list on the drawing defines the report. Report every part you find in
`bom_parts`, and put any per-part technical data you can read into
`parts_on_page` keyed by the part number exactly as printed on the drawing.
"""


class PartExtractor:
    """Extracts drawing information and attributes it to part rows."""

    #: findings categories that are worth surfacing even without a part match
    ALL_CATEGORIES = (
        "dimension", "tolerance", "hole", "weld", "gdt", "datum",
        "surface_finish", "material", "note", "bom", "view",
        "title_block", "revision", "other",
    )

    def __init__(self, client: Optional[GeminiClient] = None) -> None:
        self.client = client or GeminiClient()

    def is_available(self) -> bool:
        return self.client.is_available()

    @property
    def unavailable_reason(self) -> str:
        return self.client.unavailable_reason

    # ------------------------------------------------------------------
    # Page analysis
    # ------------------------------------------------------------------

    def analyze_page(
        self,
        page: ProcessedPage,
        ocr_text: str,
        parts: Sequence[PartInput],
    ) -> dict[str, Any]:
        """Analyse one page.

        Returns a dict with ``evidence`` (list of ``(part_no, FieldEvidence)``),
        ``bom_parts``, ``title_block``, ``findings``, ``part_numbers``,
        ``summary``, ``notes`` and ``error``.
        """
        blank: dict[str, Any] = {
            "evidence": [],
            "bom_parts": [],
            "title_block": None,
            "findings": [],
            "part_numbers": [],
            "summary": "",
            "page_type": "",
            "notes": "",
            "error": None,
        }

        if not self.is_available():
            blank["error"] = self.unavailable_reason
            return blank

        prompt = PAGE_PROMPT.format(
            parts_block=self._format_parts(parts),
            field_guidance=FIELD_GUIDANCE,
            ocr_text=(ocr_text or "(no text could be recognised on this page)")[:14000],
        )

        try:
            image_bytes = page.to_vlm_bytes()
        except Exception as e:
            blank["error"] = f"Could not encode page image: {e}"
            return blank

        try:
            parsed = self.client.generate_json(prompt, images=[image_bytes])
        except GeminiUnavailable as e:
            blank["error"] = str(e)
            return blank
        except ValueError as e:
            logger.warning("Page %d: unparseable VLM response: %s", page.page_number, e)
            blank["error"] = f"Model returned an unreadable response: {e}"
            return blank
        except Exception as e:
            logger.error("Page %d: VLM call failed: %s", page.page_number, e)
            blank["error"] = str(e)
            return blank

        return self._parse_page_response(parsed, page.page_number, parts)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_page_response(
        self,
        parsed: dict,
        page_number: int,
        parts: Sequence[PartInput],
    ) -> dict[str, Any]:
        evidence: list[tuple[str, FieldEvidence]] = []
        findings: list[DrawingFinding] = []
        part_numbers: list[str] = []

        lookup = {p.normalised_part_no(): p.part_no for p in parts if p.part_no}
        single_part = parts[0].part_no if len(parts) == 1 and parts[0].part_no else None
        discovery = not lookup

        # --- BOM table -------------------------------------------------
        bom_parts: list[DiscoveredPart] = []
        for raw in self._as_list(parsed.get("bom_parts")):
            discovered = self._build_discovered_part(raw, page_number)
            if discovered is not None:
                bom_parts.append(discovered)

        # --- per-part field data ---------------------------------------
        for entry in self._as_list(parsed.get("parts_on_page")):
            if not isinstance(entry, dict):
                continue

            raw_part_no = self._clean_str(entry.get("part_no"))
            matched = self._clean_str(entry.get("matched_user_part_no"))
            resolved = self._resolve_part_no(
                raw_part_no, matched, lookup, single_part, discovery
            )

            if raw_part_no:
                part_numbers.append(raw_part_no)

            if not resolved:
                # Field data we cannot attribute is dropped from the report but
                # kept visible as findings so it is never silently lost.
                for field, payload in self._as_dict(entry.get("fields")).items():
                    data = self._as_dict(payload)
                    value = self._clean_str(data.get("value"))
                    if value:
                        findings.append(
                            DrawingFinding(
                                category=self._normalise_field_name(field),
                                value=value,
                                detail=(
                                    f"Found for unmatched part "
                                    f"{raw_part_no or 'unknown'}"
                                ),
                                page_number=page_number,
                                part_no=raw_part_no or None,
                                confidence=self._clean_float(data.get("confidence")),
                            )
                        )
                continue

            for field, payload in self._as_dict(entry.get("fields")).items():
                ev = self._build_evidence(field, payload, page_number)
                if ev is None:
                    continue
                if self._is_development_view_reading(ev):
                    # The reading stays visible as a finding so nothing is
                    # silently lost, but it can never fill an L/W/H cell.
                    findings.append(
                        DrawingFinding(
                            category="dimension",
                            value=ev.value,
                            detail=(
                                f"Development/flat-pattern view reading "
                                f"excluded from {ev.field}"
                            ),
                            page_number=page_number,
                            part_no=resolved,
                            confidence=ev.confidence,
                            source="vlm",
                        )
                    )
                    continue
                evidence.append((resolved, ev))

        # A BOM row is itself evidence for that part's description and dwg no.
        for part in bom_parts:
            key = part.normalised_part_no()
            target = lookup.get(key) if lookup else part.part_no
            if not target and lookup:
                continue
            for field, value in (
                ("description", part.description),
                ("dwg_no", part.dwg_no),
            ):
                if value:
                    evidence.append(
                        (
                            target,
                            FieldEvidence(
                                field=field,
                                value=value,
                                page_number=page_number,
                                confidence=max(part.confidence, 0.6),
                                source_text=f"BOM row {part.s_no or '?'}: {part.part_no}",
                                reasoning="Read from the parts-list table",
                            ),
                        )
                    )

        # --- title block -----------------------------------------------
        # Kept separate from bom_parts: on a single-part drawing this is the
        # only thing that identifies the part, but on an assembly sheet it
        # names the assembly and must NOT become a component row.
        title_block = self._build_discovered_part(
            parsed.get("title_block"), page_number
        )

        # The title block is evidence for its own part only when this page has
        # no parts list, or when it names a part the operator supplied. On an
        # assembly sheet it describes the assembly, so using it would stamp the
        # assembly's title and number onto an unrelated component.
        if title_block and (not bom_parts or lookup):
            target = (
                lookup.get(title_block.normalised_part_no())
                if lookup
                else title_block.part_no
            )
            if target:
                for field, value in (
                    ("description", title_block.description),
                    ("dwg_no", title_block.dwg_no),
                ):
                    if value:
                        evidence.append(
                            (
                                target,
                                FieldEvidence(
                                    field=field,
                                    value=value,
                                    page_number=page_number,
                                    confidence=max(title_block.confidence, 0.6),
                                    source_text=f"Title block: {title_block.part_no}",
                                    reasoning="Read from the title block",
                                ),
                            )
                        )

        # --- free findings ---------------------------------------------
        for raw in self._as_list(parsed.get("findings")):
            finding = self._build_finding(raw, page_number)
            if finding is not None:
                findings.append(finding)

        return {
            "evidence": evidence,
            "bom_parts": bom_parts,
            "title_block": title_block,
            "findings": findings,
            "part_numbers": part_numbers,
            "summary": self._clean_str(parsed.get("page_summary")),
            "page_type": self._clean_str(parsed.get("page_type")),
            "notes": self._clean_str(parsed.get("notes")),
            "error": None,
        }

    def _build_discovered_part(
        self, raw: Any, page_number: int
    ) -> Optional[DiscoveredPart]:
        data = self._as_dict(raw)
        part_no = self._clean_str(data.get("part_no"))
        if not part_no:
            return None
        return DiscoveredPart(
            part_no=part_no,
            description=self._clean_str(data.get("description")) or None,
            dwg_no=self._clean_str(data.get("dwg_no")) or None,
            quantity=self._clean_str(data.get("quantity")) or None,
            s_no=self._clean_str(data.get("s_no")) or None,
            page_number=page_number,
            confidence=self._clean_float(data.get("confidence"), default=0.7),
        )

    def _build_evidence(
        self, field: str, payload: Any, page_number: int
    ) -> Optional[FieldEvidence]:
        field = self._normalise_field_name(field)
        if field not in EXTRACTABLE_FIELDS:
            return None

        data = self._as_dict(payload)
        # Tolerate the model answering with a bare scalar instead of an object.
        if not data and isinstance(payload, (str, int, float)):
            data = {"value": payload, "confidence": 0.5}

        value = self._clean_str(data.get("value"))
        if not value or value.lower() in {"null", "none", "unknown"}:
            return None

        source_text = self._clean_str(data.get("source_text"))
        confidence = self._clean_float(data.get("confidence"))

        # Rule 4 of the prompt: no quote from the drawing, no report value.
        # Downgrade rather than drop, so the UI can still show what was seen.
        if not source_text:
            confidence = min(confidence, 0.35)

        return FieldEvidence(
            field=field,
            value=value,
            unit=self._clean_str(data.get("unit")) or None,
            page_number=page_number,
            confidence=confidence,
            source_text=source_text or None,
            reasoning=self._clean_str(data.get("reasoning")) or None,
        )

    @staticmethod
    def _is_development_view_reading(ev: FieldEvidence) -> bool:
        """True when an L/W/H reading comes from a development/flat-pattern view."""
        if ev.field not in _LENGTH_FIELDS:
            return False
        haystack = " ".join(
            part for part in (ev.source_text or "", ev.reasoning or "") if part
        )
        return bool(_DEVELOPMENT_VIEW_RE.search(haystack))

    def _build_finding(self, raw: Any, page_number: int) -> Optional[DrawingFinding]:
        data = self._as_dict(raw)
        if not data:
            if isinstance(raw, str) and raw.strip():
                return DrawingFinding(
                    category="other",
                    value=raw.strip(),
                    page_number=page_number,
                    confidence=0.5,
                )
            return None

        value = self._clean_str(data.get("value"))
        if not value:
            return None

        category = (self._clean_str(data.get("category")) or "other").lower()
        if category not in self.ALL_CATEGORIES:
            category = "other"

        return DrawingFinding(
            category=category,
            value=value,
            detail=self._clean_str(data.get("detail")) or None,
            page_number=page_number,
            part_no=self._clean_str(data.get("part_no")) or None,
            confidence=self._clean_float(data.get("confidence")),
            source="vlm",
        )

    # ------------------------------------------------------------------
    # Part matching
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_key(value: str) -> str:
        return "".join(ch for ch in (value or "") if ch.isalnum()).upper()

    def _resolve_part_no(
        self,
        raw_part_no: str,
        matched: str,
        lookup: dict[str, str],
        single_part: Optional[str],
        discovery: bool,
    ) -> Optional[str]:
        """Map a part number seen on the drawing to a report row.

        In discovery mode the drawing's own part number *is* the row key, so it
        passes through unchanged. Otherwise matching is punctuation- and
        case-insensitive, because the same part is routinely written BR-1042,
        BR1042 and br 1042 across a drawing set.
        """
        if discovery:
            return raw_part_no or matched or None

        for candidate in (matched, raw_part_no):
            key = self._normalise_key(candidate)
            if key and key in lookup:
                return lookup[key]

        # Containment, e.g. drawing shows "BR1042-01" for user part "BR1042".
        for candidate in (matched, raw_part_no):
            key = self._normalise_key(candidate)
            if not key:
                continue
            hits = [
                original
                for norm, original in lookup.items()
                if norm and (norm in key or key in norm)
            ]
            if len(hits) == 1:
                return hits[0]

        # A single-part job with no part number printed anywhere still has an
        # unambiguous owner.
        if single_part and not raw_part_no and not matched:
            return single_part
        return None

    @staticmethod
    def _format_parts(parts: Sequence[PartInput]) -> str:
        supplied = [p for p in parts if p.part_no and not p.discovered]
        if not supplied:
            return _DISCOVERY_BLOCK

        lines = []
        for p in supplied:
            known = [
                f"{FIELD_TO_COLUMN[f]}={p.user_value(f)}"
                for f in EXTRACTABLE_FIELDS
                if p.user_value(f)
            ]
            detail = "; ".join(known) if known else "no other fields supplied"
            lines.append(f"- PART NO: {p.part_no} | already known: {detail}")
        return _SUPPLIED_BLOCK.format(rows="\n".join(lines))

    # ------------------------------------------------------------------
    # Coercion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_field_name(field: str) -> str:
        key = re.sub(r"[^a-z0-9]+", "_", str(field).strip().lower()).strip("_")
        aliases = {
            "weight": "weight_kg",
            "weight_in_kg": "weight_kg",
            "mass": "weight_kg",
            "mass_kg": "weight_kg",
            "sno": "s_no",
            "partno": "part_no",
            "part_number": "part_no",
            "desc": "description",
            "dwgno": "dwg_no",
            "dwg_number": "dwg_no",
            "drawing_no": "dwg_no",
            "drawing_number": "dwg_no",
            "thk": "thickness",
            "material_thickness": "thickness",
            "len": "length",
            "length_mm": "length",
            "width_mm": "width",
            "height_mm": "height",
            "overall_length": "length",
            "overall_width": "width",
            "overall_height": "height",
            "manufacturing_process": "process",
        }
        return aliases.get(key, key)

    @staticmethod
    def _as_list(value: Any) -> list:
        if isinstance(value, list):
            return value
        if value in (None, "", {}):
            return []
        return [value]

    @staticmethod
    def _as_dict(value: Any) -> dict:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _clean_str(value: Any) -> str:
        if value is None or isinstance(value, (dict, list)):
            return ""
        text = str(value).strip()
        return "" if text.lower() in {"null", "none", "nan"} else text

    @staticmethod
    def _clean_float(value: Any, default: float = 0.5) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return default
        if result != result:  # NaN
            return default
        return max(0.0, min(1.0, result))
