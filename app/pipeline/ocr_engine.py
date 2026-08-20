"""OCR module using PaddleOCR for text detection and recognition.

Wraps PaddleOCR for engineering drawing text extraction with bounding boxes,
confidence scores, and structured output.
"""

from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

# Lazy import – PaddleOCR is heavy
_ocr_instance = None


def _get_ocr():
    global _ocr_instance
    if _ocr_instance is None:
        try:
            from paddleocr import PaddleOCR
            _ocr_instance = PaddleOCR(
                use_angle_cls=True,
                lang=settings.OCR_LANG,
                use_gpu=settings.OCR_USE_GPU,
                det_db_thresh=settings.OCR_DET_DB_THRESH,
                det_db_box_thresh=settings.OCR_DET_DB_BOX_THRESH,
                show_log=False,
            )
            logger.info("PaddleOCR engine initialised")
        except ImportError:
            logger.warning("PaddleOCR not installed – OCR module will return empty results")
            return None
    return _ocr_instance


class OCRResult:
    """Single OCR detection result."""

    def __init__(
        self,
        text: str,
        confidence: float,
        bbox: list[list[float]],
        page_number: int = 1,
    ) -> None:
        self.text = text
        self.confidence = confidence
        self.bbox = bbox  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        self.page_number = page_number

    @property
    def normalised_bbox(self) -> list[float]:
        """Return [x_min, y_min, x_max, y_max] normalised to 0-1."""
        if not self.bbox:
            return [0, 0, 0, 0]
        xs = [p[0] for p in self.bbox]
        ys = [p[1] for p in self.bbox]
        return [min(xs), min(ys), max(xs), max(ys)]


class OCREngine:
    """High-level OCR interface for engineering drawings."""

    def __init__(self) -> None:
        self.ocr = _get_ocr()

    def is_available(self) -> bool:
        return self.ocr is not None

    def extract_text(
        self,
        image: np.ndarray,
        page_number: int = 1,
        min_confidence: float = 0.3,
    ) -> list[OCRResult]:
        if self.ocr is None:
            logger.warning("OCR engine not available")
            return []

        results = self.ocr.ocr(image, cls=True)
        if not results or not results[0]:
            return []

        ocr_items: list[OCRResult] = []
        for line in results[0]:
            bbox = line[0]
            text = line[1][0]
            conf = float(line[1][1])
            if conf >= min_confidence:
                ocr_items.append(
                    OCRResult(
                        text=text.strip(),
                        confidence=conf,
                        bbox=bbox,
                        page_number=page_number,
                    )
                )

        logger.info(
            "Page %d: extracted %d text regions (min_conf=%.2f)",
            page_number,
            len(ocr_items),
            min_confidence,
        )
        return ocr_items

    def extract_text_regions(
        self,
        image: np.ndarray,
        page_number: int = 1,
    ) -> dict[str, list[OCRResult]]:
        """Group OCR results by approximate vertical position (row-based)."""
        all_results = self.extract_text(image, page_number)
        if not all_results:
            return {}

        # Sort by Y position
        all_results.sort(key=lambda r: r.normalised_bbox[1])

        groups: dict[str, list[OCRResult]] = {}
        current_y = -1.0
        group_idx = 0
        y_tolerance = 0.02  # 2% of page height

        for result in all_results:
            y_center = (result.normalised_bbox[1] + result.normalised_bbox[3]) / 2
            if current_y < 0 or abs(y_center - current_y) > y_tolerance:
                group_idx += 1
                current_y = y_center
            key = f"row_{group_idx}"
            groups.setdefault(key, []).append(result)

        return groups

    def extract_with_paddlex(self, image: np.ndarray) -> dict:
        """Attempt PaddleX pipeline for layout analysis + OCR."""
        try:
            from paddlex import create_pipeline
            pipeline = create_pipeline(pipeline="PP-ChatOCRv3-doc")
            result = pipeline.predict(image)
            return result
        except Exception as e:
            logger.debug("PaddleX not available: %s", e)
            return {}
