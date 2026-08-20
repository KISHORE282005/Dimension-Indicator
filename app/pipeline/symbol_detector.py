"""Symbol detection hook for custom YOLO11 models.

This is the extension point for detecting drawing objects that OCR cannot read
and a VLM localises only loosely: GD&T feature control frames, welding symbols,
hole callouts, datum triangles, section markers, surface finish symbols.

Nothing here is speculative scaffolding that has to be rewritten later. The
pipeline already calls :meth:`detect` for every page and merges what comes back
into the findings list. Training a model and pointing ``YOLO_MODEL_PATH`` at
the weights turns it on - no other code changes.

Until weights exist, :meth:`detect` returns an empty list, so the detector is
inert rather than fabricating boxes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from app.config import settings
from app.models.part_schemas import DrawingFinding
from app.pipeline.document_processor import ProcessedPage

logger = logging.getLogger(__name__)


#: Maps YOLO class names to the finding categories the rest of the app uses.
#: Extend this alongside the model's training classes.
CLASS_TO_CATEGORY: dict[str, str] = {
    "gdt": "gdt",
    "gdt_frame": "gdt",
    "feature_control_frame": "gdt",
    "weld": "weld",
    "weld_symbol": "weld",
    "welding_symbol": "weld",
    "hole": "hole",
    "hole_callout": "hole",
    "datum": "datum",
    "datum_feature": "datum",
    "section_marker": "view",
    "detail_marker": "view",
    "surface_finish": "surface_finish",
    "roughness": "surface_finish",
    "dimension": "dimension",
    "tolerance": "tolerance",
}


class SymbolDetector:
    """Optional YOLO11 detector for engineering symbols."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        confidence_threshold: Optional[float] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        self.model_path = Path(model_path or settings.YOLO_MODEL_PATH)
        self.confidence_threshold = (
            settings.YOLO_CONFIDENCE_THRESHOLD
            if confidence_threshold is None
            else confidence_threshold
        )
        self.enabled = settings.YOLO_ENABLE_CUSTOM if enabled is None else enabled
        self._model: Any = None
        self.status_note: str = ""
        self._load()

    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self.enabled:
            self.status_note = (
                "Disabled. Set YOLO_ENABLE_CUSTOM=true and provide "
                "YOLO_MODEL_PATH to enable custom symbol detection."
            )
            return

        if not self.model_path.exists():
            self.status_note = f"No weights found at {self.model_path}."
            logger.warning("YOLO enabled but %s", self.status_note)
            return

        try:
            from ultralytics import YOLO
        except ImportError:
            self.status_note = "ultralytics is not installed (pip install ultralytics)."
            logger.warning(self.status_note)
            return

        try:
            self._model = YOLO(str(self.model_path))
            self.status_note = f"Loaded {self.model_path.name}."
            logger.info("YOLO symbol detector loaded from %s", self.model_path)
        except Exception as e:
            self.status_note = f"Failed to load weights: {e}"
            logger.error("YOLO load failed: %s", e)

    def is_available(self) -> bool:
        return self._model is not None

    # ------------------------------------------------------------------

    def detect(self, page: ProcessedPage) -> list[DrawingFinding]:
        """Detect engineering symbols on a page.

        Returns an empty list when no model is loaded, which is the normal
        state until custom weights are trained.
        """
        if not self.is_available():
            return []

        try:
            # Detection runs on the clean render: binarised input loses the
            # thin strokes that distinguish, say, a datum triangle from a
            # dimension arrowhead.
            predictions = self._model.predict(
                page.original_image,
                conf=self.confidence_threshold,
                verbose=False,
            )
        except Exception as e:
            logger.error("YOLO inference failed on page %d: %s", page.page_number, e)
            return []

        findings: list[DrawingFinding] = []
        names = getattr(self._model, "names", {}) or {}

        for prediction in predictions:
            boxes = getattr(prediction, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                try:
                    class_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
                except (IndexError, TypeError, ValueError):
                    continue

                raw_name = str(names.get(class_id, f"class_{class_id}"))
                category = CLASS_TO_CATEGORY.get(raw_name.lower(), "other")

                findings.append(
                    DrawingFinding(
                        category=category,
                        value=raw_name.replace("_", " ").title(),
                        detail=(
                            f"Detected at ({x1:.0f}, {y1:.0f})-({x2:.0f}, {y2:.0f}) "
                            f"on page {page.page_number}"
                        ),
                        page_number=page.page_number,
                        confidence=confidence,
                        source="yolo",
                    )
                )

        logger.info(
            "YOLO: %d symbol(s) detected on page %d", len(findings), page.page_number
        )
        return findings
