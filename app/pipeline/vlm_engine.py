"""VLM reasoning layer using Gemini 2.5 Pro.

Sends page images and OCR text to Gemini for engineering interpretation.
All VLM outputs are clearly tagged as AI interpretations, never as verified facts.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Optional

import cv2
import numpy as np

from app.config import settings
from app.models.schemas import (
    AIInterpretation,
    BaseExtractedItem,
    BOMItem,
    DatumItem,
    DimensionItem,
    DrawingMetadata,
    ExtractionCategory,
    GDTItem,
    HoleItem,
    ManufacturingNote,
    MaterialItem,
    SectionView,
    SourceType,
    SurfaceFinishItem,
    WeldingItem,
)

logger = logging.getLogger(__name__)

# Lazy client
_genai_client = None


def _get_gemini():
    global _genai_client
    if _genai_client is not None:
        return _genai_client
    try:
        import google.generativeai as genai
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
        _genai_client = genai.GenerativeModel(settings.GEMINI_MODEL)
        logger.info("Gemini model %s initialised", settings.GEMINI_MODEL)
        return _genai_client
    except ImportError:
        logger.warning("google-generativeai not installed")
        return None
    except Exception as e:
        logger.error("Failed to init Gemini: %s", e)
        return None


# ------------------------------------------------------------------
# Prompt templates
# ------------------------------------------------------------------

ENGINEERING_EXTRACTION_PROMPT = """\
You are an expert engineering document analyst. Analyze this engineering drawing page and extract ALL technical information.

Return a JSON object with the following structure. Extract ONLY what you can clearly see. Do NOT invent or guess values.

{{
  "drawing_metadata": {{
    "drawing_number": "...",
    "revision": "...",
    "title": "...",
    "scale": "...",
    "drawn_by": "...",
    "checked_by": "...",
    "approved_by": "...",
    "date": "...",
    "company": "...",
    "drawing_standard": "..."
  }},
  "dimensions": [
    {{
      "value": "the dimension text as shown",
      "dimension_type": "linear|angular|radial|diameter",
      "nominal_value": numeric_value_or_null,
      "unit": "mm|inches|degrees",
      "bounding_box": [x_min, y_min, x_max, y_max] normalised 0-1
    }}
  ],
  "tolerances": [
    {{
      "value": "tolerance text",
      "nominal_value": numeric_or_null,
      "upper_tolerance": numeric_or_null,
      "lower_tolerance": numeric_or_null,
      "fit_class": "H7|g6|etc or null"
    }}
  ],
  "holes": [
    {{
      "value": "hole description text",
      "hole_type": "through|blind|tapped|countersink|counterbore",
      "diameter": numeric_or_null,
      "depth": numeric_or_null,
      "thread_spec": "M6x1.0 etc or null",
      "quantity": int_or_null
    }}
  ],
  "welding_items": [
    {{
      "value": "weld symbol text",
      "weld_type": "fillet|groove|plug|spot|seam",
      "weld_size": "size text",
      "joint_type": "butt|corner|edge|lap|tee",
      "arrow_side": bool,
      "other_side": bool
    }}
  ],
  "gd_t_items": [
    {{
      "value": "feature control frame text",
      "characteristic": "flatness|position|perpendicularity|runout|concentricity|etc",
      "symbol": "symbol text",
      "tolerance_value": numeric_or_null,
      "datum_references": ["A", "B", ...],
      "modifier": "MMC|LMC|RFS|null"
    }}
  ],
  "datums": [
    {{
      "value": "datum label",
      "datum_label": "A|B|C|...",
      "datum_type": "plane|axis|point|center-plane",
      "feature_description": "what feature this datum references"
    }}
  ],
  "surface_finishes": [
    {{
      "value": "surface finish text",
      "roughness_value": numeric_or_null,
      "roughness_unit": "Ra",
      "surface_method": "machined|ground|turned|etc"
    }}
  ],
  "materials": [
    {{
      "value": "material text",
      "material_spec": "ASTM A36 etc",
      "material_name": "Steel|Aluminum|etc",
      "material_grade": "grade text"
    }}
  ],
  "manufacturing_notes": [
    {{
      "value": "note number",
      "note_text": "full note text",
      "note_type": "general|finish|heat-treat|tolerance_block"
    }}
  ],
  "bom_items": [
    {{
      "value": "item number",
      "part_number": "...",
      "description": "...",
      "quantity": int_or_null,
      "material": "..."
    }}
  ],
  "section_views": [
    {{
      "value": "section label",
      "section_label": "A-A|B-B|...",
      "view_direction": "direction text"
    }}
  ],
  "detail_views": [
    {{
      "value": "detail label",
      "detail_label": "Detail A|Detail B|...",
      "scale": "scale text"
    }}
  ],
  "critical_characteristics": [
    {{
      "value": "characteristic text",
      "characteristic_type": "safety|functional|regulatory",
      "symbol": "symbol text"
    }}
  ],
  "other_annotations": [
    {{
      "value": "annotation text",
      "category": "annotation type"
    }}
  ]
}}

Return ONLY valid JSON. If a category has no items, return an empty list [].
If drawing_metadata is not visible, return null.
Never fabricate values. If something is unclear, note it in the value field with [UNCLEAR].
"""

VISION_ANALYSIS_PROMPT = """\
You are an expert engineering symbol reader. Examine this cropped region of an engineering drawing.
This region may contain: welding symbols, GD&T feature control frames, surface finish symbols,
datum indicators, hole callouts, or dimension annotations.

Return a JSON object:
{{
  "detected_type": "welding|gd_t|surface_finish|datum|hole_callout|dimension|annotation|unknown",
  "interpretation": "detailed description of what you see",
  "extracted_data": {{
    // Type-specific fields based on detected_type
  }},
  "confidence": 0.0_to_1.0,
  "notes": "any caveats or uncertainty"
}}

Only report what you can clearly see. Return ONLY valid JSON.
"""


class VLMEngine:
    """Vision-Language Model engine for engineering drawing interpretation."""

    def __init__(self) -> None:
        self.model = _get_gemini()
        self.config = {
            "temperature": settings.GEMINI_TEMPERATURE,
            "max_output_tokens": settings.GEMINI_MAX_TOKENS,
        }

    def is_available(self) -> bool:
        return self.model is not None

    def _image_to_part(self, image: np.ndarray) -> dict:
        """Convert numpy image to Gemini-compatible image part."""
        _, buf = cv2.imencode(".png", image)
        b64 = base64.b64encode(buf).decode("utf-8")
        return {
            "inline_data": {
                "mime_type": "image/png",
                "data": b64,
            }
        }

    def _parse_json_response(self, text: str) -> dict:
        """Extract JSON from Gemini response text."""
        text = text.strip()
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try extracting from markdown code block
        import re
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        logger.warning("Failed to parse VLM JSON response")
        return {}

    def analyze_page(
        self,
        page_image: np.ndarray,
        ocr_text: str,
        page_number: int,
    ) -> AIInterpretation:
        """Send full page image + OCR context to Gemini for engineering analysis."""
        if not self.is_available():
            return AIInterpretation(
                page_number=page_number,
                interpretation_text="VLM engine not available",
                confidence=0.0,
                model_used="none",
            )

        prompt = ENGINEERING_EXTRACTION_PROMPT.format()
        image_part = self._image_to_part(page_image)
        text_part = f"OCR extracted text from this page:\n```\n{ocr_text}\n```\n\nAnalyze the drawing."

        try:
            response = self.model.generate_content(
                [image_part, text_part, prompt],
                generation_config=self.config,
            )
            raw_text = response.text
            parsed = self._parse_json_response(raw_text)
            items = self._parsed_to_items(parsed, page_number)

            return AIInterpretation(
                page_number=page_number,
                interpretation_text=raw_text,
                extracted_items=items,
                confidence=self._compute_avg_confidence(parsed),
                model_used=settings.GEMINI_MODEL,
                prompt_used=ENGINEERING_EXTRACTION_PROMPT[:500] + "...",
            )
        except Exception as e:
            logger.error("Gemini analysis failed for page %d: %s", page_number, e)
            return AIInterpretation(
                page_number=page_number,
                interpretation_text=f"VLM analysis failed: {e}",
                confidence=0.0,
                model_used=settings.GEMINI_MODEL,
            )

    def analyze_region(
        self,
        region_image: np.ndarray,
        context: str,
        page_number: int,
    ) -> dict:
        """Analyze a cropped region for specific engineering symbols."""
        if not self.is_available():
            return {"detected_type": "unknown", "interpretation": "VLM not available", "confidence": 0.0}

        image_part = self._image_to_part(region_image)
        text_part = f"Context: {context}\n\nAnalyze this engineering drawing region."

        try:
            response = self.model.generate_content(
                [image_part, text_part, VISION_ANALYSIS_PROMPT],
                generation_config=self.config,
            )
            return self._parse_json_response(response.text)
        except Exception as e:
            logger.error("Region analysis failed: %s", e)
            return {"detected_type": "unknown", "interpretation": str(e), "confidence": 0.0}

    # ------------------------------------------------------------------
    # Response parsing helpers
    # ------------------------------------------------------------------

    def _parsed_to_items(self, parsed: dict, page_number: int) -> list[BaseExtractedItem]:
        items: list[BaseExtractedItem] = []

        # Drawing metadata
        dm = parsed.get("drawing_metadata")
        if dm and isinstance(dm, dict) and any(v for v in dm.values() if v):
            items.append(
                DrawingMetadata(
                    value=dm.get("title") or dm.get("drawing_number") or "metadata",
                    category=ExtractionCategory.DRAWING_INFO,
                    page_number=page_number,
                    confidence=0.8,
                    source_type=SourceType.VLM,
                    drawing_number=dm.get("drawing_number"),
                    revision=dm.get("revision"),
                    title=dm.get("title"),
                    scale=dm.get("scale"),
                    drawn_by=dm.get("drawn_by"),
                    checked_by=dm.get("checked_by"),
                    approved_by=dm.get("approved_by"),
                    date=dm.get("date"),
                    company=dm.get("company"),
                    drawing_standard=dm.get("drawing_standard"),
                )
            )

        # Dimensions
        for d in parsed.get("dimensions", []):
            items.append(
                DimensionItem(
                    value=d.get("value", ""),
                    category=ExtractionCategory.DIMENSION,
                    page_number=page_number,
                    confidence=0.7,
                    source_type=SourceType.VLM,
                    dimension_type=d.get("dimension_type"),
                    nominal_value=d.get("nominal_value"),
                    unit=d.get("unit"),
                    bounding_box=d.get("bounding_box"),
                )
            )

        # Tolerances
        for t in parsed.get("tolerances", []):
            items.append(
                ToleranceItem(
                    value=t.get("value", ""),
                    category=ExtractionCategory.TOLERANCE,
                    page_number=page_number,
                    confidence=0.7,
                    source_type=SourceType.VLM,
                    nominal_value=t.get("nominal_value"),
                    upper_tolerance=t.get("upper_tolerance"),
                    lower_tolerance=t.get("lower_tolerance"),
                    fit_class=t.get("fit_class"),
                )
            )

        # Holes
        for h in parsed.get("holes", []):
            items.append(
                HoleItem(
                    value=h.get("value", ""),
                    category=ExtractionCategory.HOLE,
                    page_number=page_number,
                    confidence=0.7,
                    source_type=SourceType.VLM,
                    hole_type=h.get("hole_type"),
                    diameter=h.get("diameter"),
                    depth=h.get("depth"),
                    thread_spec=h.get("thread_spec"),
                    quantity=h.get("quantity"),
                )
            )

        # Welding
        for w in parsed.get("welding_items", []):
            items.append(
                WeldingItem(
                    value=w.get("value", ""),
                    category=ExtractionCategory.WELDING,
                    page_number=page_number,
                    confidence=0.7,
                    source_type=SourceType.VLM,
                    weld_type=w.get("weld_type"),
                    weld_size=w.get("weld_size"),
                    joint_type=w.get("joint_type"),
                    arrow_side=w.get("arrow_side", False),
                    other_side=w.get("other_side", False),
                )
            )

        # GD&T
        for g in parsed.get("gd_t_items", []):
            items.append(
                GDTItem(
                    value=g.get("value", ""),
                    category=ExtractionCategory.GD_T,
                    page_number=page_number,
                    confidence=0.7,
                    source_type=SourceType.VLM,
                    characteristic=g.get("characteristic"),
                    symbol=g.get("symbol"),
                    tolerance_value=g.get("tolerance_value"),
                    datum_references=g.get("datum_references", []),
                    modifier=g.get("modifier"),
                )
            )

        # Datums
        for dt in parsed.get("datums", []):
            items.append(
                DatumItem(
                    value=dt.get("value", ""),
                    category=ExtractionCategory.DATUM,
                    page_number=page_number,
                    confidence=0.8,
                    source_type=SourceType.VLM,
                    datum_label=dt.get("datum_label"),
                    datum_type=dt.get("datum_type"),
                    feature_description=dt.get("feature_description"),
                )
            )

        # Surface finishes
        for sf in parsed.get("surface_finishes", []):
            items.append(
                SurfaceFinishItem(
                    value=sf.get("value", ""),
                    category=ExtractionCategory.SURFACE_FINISH,
                    page_number=page_number,
                    confidence=0.7,
                    source_type=SourceType.VLM,
                    roughness_value=sf.get("roughness_value"),
                    roughness_unit=sf.get("roughness_unit", "Ra"),
                    surface_method=sf.get("surface_method"),
                )
            )

        # Materials
        for m in parsed.get("materials", []):
            items.append(
                MaterialItem(
                    value=m.get("value", ""),
                    category=ExtractionCategory.MATERIAL,
                    page_number=page_number,
                    confidence=0.7,
                    source_type=SourceType.VLM,
                    material_spec=m.get("material_spec"),
                    material_name=m.get("material_name"),
                    material_grade=m.get("material_grade"),
                )
            )

        # Manufacturing notes
        for n in parsed.get("manufacturing_notes", []):
            items.append(
                ManufacturingNote(
                    value=n.get("value", ""),
                    category=ExtractionCategory.MANUFACTURING_NOTE,
                    page_number=page_number,
                    confidence=0.8,
                    source_type=SourceType.VLM,
                    note_text=n.get("note_text", ""),
                    note_type=n.get("note_type"),
                )
            )

        # BOM items
        for b in parsed.get("bom_items", []):
            items.append(
                BOMItem(
                    value=b.get("value", ""),
                    category=ExtractionCategory.BOM,
                    page_number=page_number,
                    confidence=0.7,
                    source_type=SourceType.VLM,
                    part_number=b.get("part_number"),
                    description=b.get("description"),
                    quantity=b.get("quantity"),
                    material=b.get("material"),
                )
            )

        # Section views
        for sv in parsed.get("section_views", []):
            items.append(
                SectionView(
                    value=sv.get("value", ""),
                    category=ExtractionCategory.SECTION_VIEW,
                    page_number=page_number,
                    confidence=0.8,
                    source_type=SourceType.VLM,
                    section_label=sv.get("section_label"),
                    view_direction=sv.get("view_direction"),
                )
            )

        # Detail views
        for dv in parsed.get("detail_views", []):
            items.append(
                DetailView(
                    value=dv.get("value", ""),
                    category=ExtractionCategory.DETAIL_VIEW,
                    page_number=page_number,
                    confidence=0.8,
                    source_type=SourceType.VLM,
                    detail_label=dv.get("detail_label"),
                    scale=dv.get("scale"),
                )
            )

        return items

    def _compute_avg_confidence(self, parsed: dict) -> float:
        confidences = []
        for key in ["dimensions", "tolerances", "holes", "welding_items", "gd_t_items"]:
            for item in parsed.get(key, []):
                if isinstance(item, dict) and "confidence" in item:
                    confidences.append(float(item["confidence"]))
        return sum(confidences) / len(confidences) if confidences else 0.6
