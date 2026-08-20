"""OCR module for engineering drawing text extraction.

Primary engine is PaddleOCR. Its Python API changed incompatibly between the
2.x and 3.x releases, so construction and invocation are both probed at runtime
rather than pinned to one signature.

When PaddleOCR is not installed the engine degrades to the vector text layer
that PyMuPDF pulls straight out of the PDF. For CAD-exported drawings that text
layer is exact - it is the glyphs the CAD package wrote, not a recognition
guess - so the fallback is genuinely useful rather than a stub. It only comes
up empty for scanned or raster-only drawings, and the engine reports which
source was used so nothing silently passes as OCR that was not.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

import cv2
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

_ocr_instance: Any = None
_ocr_flavour: str = "none"
_ocr_probed: bool = False
_ocr_error: str = ""

#: PaddleOCR's inference backend is not thread-safe. Two analysis jobs running
#: concurrently - which the API's worker pool allows - will call predict() on
#: the same instance at the same time and abort the whole process with SIGSEGV,
#: taking the server down with it. Every call is serialised through this lock.
_ocr_lock = threading.Lock()

#: Guards construction, which also loads model weights.
_ocr_init_lock = threading.Lock()


def _build_paddleocr() -> tuple[Any, str, str]:
    """Construct a PaddleOCR instance, tolerating 2.x and 3.x signatures.

    Returns (instance, flavour, error_message).
    """
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        return None, "none", (
            "PaddleOCR not installed. Install with: "
            "pip install paddlepaddle paddleocr"
        )
    except Exception as e:  # pragma: no cover - broken install
        return None, "none", f"PaddleOCR import failed: {e}"

    # PaddleOCR 3.x: the angle/gpu/log kwargs were removed and replaced.
    v3_kwargs = {
        "lang": settings.OCR_LANG,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": True,
    }
    # PaddleOCR 2.x signature.
    v2_kwargs = {
        "lang": settings.OCR_LANG,
        "use_angle_cls": True,
        "use_gpu": settings.OCR_USE_GPU,
        "det_db_thresh": settings.OCR_DET_DB_THRESH,
        "det_db_box_thresh": settings.OCR_DET_DB_BOX_THRESH,
        "show_log": False,
    }

    for flavour, kwargs in (("paddleocr-3", v3_kwargs), ("paddleocr-2", v2_kwargs)):
        try:
            instance = PaddleOCR(**kwargs)
            logger.info("PaddleOCR initialised (%s, lang=%s)", flavour, settings.OCR_LANG)
            return instance, flavour, ""
        except TypeError as e:
            logger.debug("%s signature rejected: %s", flavour, e)
        except Exception as e:
            logger.warning("%s construction failed: %s", flavour, e)

    # Last resort: let PaddleOCR pick every default itself.
    try:
        instance = PaddleOCR(lang=settings.OCR_LANG)
        logger.info("PaddleOCR initialised with default settings")
        return instance, "paddleocr-default", ""
    except Exception as e:
        return None, "none", f"PaddleOCR could not be initialised: {e}"


def _get_ocr() -> Any:
    global _ocr_instance, _ocr_flavour, _ocr_probed, _ocr_error
    if _ocr_probed:
        return _ocr_instance
    with _ocr_init_lock:
        if not _ocr_probed:
            _ocr_instance, _ocr_flavour, _ocr_error = _build_paddleocr()
            _ocr_probed = True
            if _ocr_error:
                logger.warning(
                    "%s - falling back to the PDF vector text layer", _ocr_error
                )
    return _ocr_instance


class OCRResult:
    """A single recognised text region."""

    def __init__(
        self,
        text: str,
        confidence: float,
        bbox: list[list[float]],
        page_number: int = 1,
        source: str = "ocr",
    ) -> None:
        self.text = text
        self.confidence = confidence
        self.bbox = bbox  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] in pixels
        self.page_number = page_number
        self.source = source

    @property
    def normalised_bbox(self) -> list[float]:
        """[x_min, y_min, x_max, y_max] in the same units as `bbox`."""
        if not self.bbox:
            return [0.0, 0.0, 0.0, 0.0]
        xs = [p[0] for p in self.bbox]
        ys = [p[1] for p in self.bbox]
        return [min(xs), min(ys), max(xs), max(ys)]

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "bbox": self.normalised_bbox,
            "page_number": self.page_number,
            "source": self.source,
        }


class OCREngine:
    """High-level OCR interface for engineering drawings."""

    def __init__(self) -> None:
        self.ocr = _get_ocr()

    def is_available(self) -> bool:
        return self.ocr is not None

    @property
    def engine_name(self) -> str:
        return _ocr_flavour if self.ocr is not None else "pdf-text-layer"

    @property
    def unavailable_reason(self) -> str:
        return _ocr_error

    # ------------------------------------------------------------------
    # Recognition
    # ------------------------------------------------------------------

    def extract_text(
        self,
        image: np.ndarray,
        page_number: int = 1,
        min_confidence: float = 0.3,
    ) -> list[OCRResult]:
        """Recognise all text in a page image."""
        if self.ocr is None:
            return []

        # PaddleOCR's inference backend aborts (SIGSEGV / "Unknown exception")
        # on very large inputs. A 300 DPI A1 sheet renders to ~4096 px, which
        # crashes it every time, so detection runs on a downscaled copy and the
        # boxes are scaled back to page coordinates afterwards.
        small, scale = self._fit_for_ocr(image)

        try:
            with _ocr_lock:
                raw = self._invoke(small)
        except Exception as e:
            logger.error("OCR failed on page %d: %s", page_number, e)
            return []

        items = self._normalise_output(raw, page_number)
        if scale != 1.0:
            for item in items:
                item.bbox = [[x / scale, y / scale] for x, y in item.bbox]

        kept = [i for i in items if i.confidence >= min_confidence]

        logger.info(
            "Page %d: %d/%d text regions kept (min_conf=%.2f, engine=%s)",
            page_number,
            len(kept),
            len(items),
            min_confidence,
            _ocr_flavour,
        )
        return kept

    @staticmethod
    def _fit_for_ocr(image: np.ndarray) -> tuple[np.ndarray, float]:
        """Downscale a page so PaddleOCR can survive it.

        Returns the image to run detection on and the scale factor applied, so
        callers can map boxes back to the original page coordinates.
        """
        limit = settings.OCR_MAX_IMAGE_SIZE
        height, width = image.shape[:2]
        longest = max(height, width)
        if limit <= 0 or longest <= limit:
            return image, 1.0

        scale = limit / longest
        resized = cv2.resize(
            image,
            (max(int(width * scale), 1), max(int(height * scale), 1)),
            interpolation=cv2.INTER_AREA,
        )
        logger.info(
            "Downscaled page for OCR: %dx%d -> %dx%d (limit %d)",
            width, height, resized.shape[1], resized.shape[0], limit,
        )
        return resized, scale

    def _invoke(self, image: np.ndarray) -> Any:
        """Call whichever prediction method this PaddleOCR build exposes."""
        if _ocr_flavour == "paddleocr-2":
            try:
                return self.ocr.ocr(image, cls=True)
            except TypeError:
                return self.ocr.ocr(image)

        # 3.x prefers predict(); older builds only have ocr().
        if hasattr(self.ocr, "predict"):
            try:
                return self.ocr.predict(image)
            except TypeError:
                pass
        try:
            return self.ocr.ocr(image, cls=True)
        except TypeError:
            return self.ocr.ocr(image)

    # ------------------------------------------------------------------
    # Output normalisation
    # ------------------------------------------------------------------

    def _normalise_output(self, raw: Any, page_number: int) -> list[OCRResult]:
        """Flatten PaddleOCR's several output shapes into OCRResult objects."""
        if not raw:
            return []

        results: list[OCRResult] = []

        # Shape A (3.x): [{'rec_texts': [...], 'rec_scores': [...], 'rec_polys': [...]}]
        entries = raw if isinstance(raw, list) else [raw]
        for entry in entries:
            payload = entry
            # 3.x wraps results in an object exposing .json or dict access.
            if not isinstance(payload, (dict, list)) and hasattr(payload, "json"):
                payload = getattr(payload, "json", None) or {}
                if isinstance(payload, dict) and "res" in payload:
                    payload = payload["res"]

            if isinstance(payload, dict) and "rec_texts" in payload:
                texts = payload.get("rec_texts") or []
                scores = payload.get("rec_scores") or []
                polys = (
                    payload.get("rec_polys")
                    or payload.get("dt_polys")
                    or payload.get("rec_boxes")
                    or []
                )
                for i, text in enumerate(texts):
                    conf = float(scores[i]) if i < len(scores) else 0.0
                    poly = self._coerce_poly(polys[i]) if i < len(polys) else []
                    results.append(
                        OCRResult(str(text).strip(), conf, poly, page_number, "ocr")
                    )
                continue

            # Shape B (2.x): [[ [poly, (text, score)], ... ]]
            lines = payload
            if (
                isinstance(lines, list)
                and lines
                and isinstance(lines[0], list)
                and lines[0]
                and isinstance(lines[0][0], (list, tuple))
                and len(lines[0]) == 2
            ):
                pass  # already a list of lines
            elif isinstance(lines, list) and len(lines) == 1 and isinstance(lines[0], list):
                lines = lines[0]

            if not isinstance(lines, list):
                continue

            for line in lines:
                parsed = self._parse_v2_line(line, page_number)
                if parsed is not None:
                    results.append(parsed)

        return [r for r in results if r.text]

    @staticmethod
    def _parse_v2_line(line: Any, page_number: int) -> Optional[OCRResult]:
        if not isinstance(line, (list, tuple)) or len(line) < 2:
            return None
        poly, rec = line[0], line[1]
        if isinstance(rec, (list, tuple)) and len(rec) >= 2:
            text, conf = rec[0], rec[1]
        elif isinstance(rec, str):
            text, conf = rec, 0.0
        else:
            return None
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.0
        return OCRResult(
            str(text).strip(), conf, OCREngine._coerce_poly(poly), page_number, "ocr"
        )

    @staticmethod
    def _coerce_poly(poly: Any) -> list[list[float]]:
        """Turn any polygon/box representation into [[x,y], ...]."""
        if poly is None:
            return []
        if isinstance(poly, np.ndarray):
            poly = poly.tolist()
        if not isinstance(poly, (list, tuple)) or not poly:
            return []
        # Flat [x1, y1, x2, y2] box
        if all(isinstance(p, (int, float)) for p in poly):
            if len(poly) == 4:
                x1, y1, x2, y2 = (float(v) for v in poly)
                return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
            return []
        out: list[list[float]] = []
        for point in poly:
            if isinstance(point, np.ndarray):
                point = point.tolist()
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                out.append([float(point[0]), float(point[1])])
        return out

    # ------------------------------------------------------------------
    # Fallback: PDF vector text layer
    # ------------------------------------------------------------------

    @staticmethod
    def results_from_text_blocks(
        text_blocks: list[dict], page_number: int
    ) -> list[OCRResult]:
        """Wrap PyMuPDF text spans as OCRResults so callers see one type.

        Confidence is 0.99: these glyphs were read out of the PDF's own text
        layer, not recognised from pixels.
        """
        results: list[OCRResult] = []
        for block in text_blocks:
            text = str(block.get("text", "")).strip()
            if not text:
                continue
            bbox = block.get("bbox") or []
            poly: list[list[float]] = []
            if len(bbox) == 4:
                x1, y1, x2, y2 = (float(v) for v in bbox)
                poly = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
            results.append(
                OCRResult(text, 0.99, poly, page_number, source="pdf-text-layer")
            )
        return results

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def group_into_lines(
        self, results: list[OCRResult], y_tolerance_ratio: float = 0.6
    ) -> list[list[OCRResult]]:
        """Group regions into visual rows, then sort each row left-to-right.

        Title blocks and BOM tables only read correctly in reading order, and
        raw detection order is not reading order.
        """
        if not results:
            return []

        heights = [
            r.normalised_bbox[3] - r.normalised_bbox[1]
            for r in results
            if r.normalised_bbox[3] > r.normalised_bbox[1]
        ]
        median_h = float(np.median(heights)) if heights else 10.0
        tolerance = max(median_h * y_tolerance_ratio, 1.0)

        ordered = sorted(results, key=lambda r: r.normalised_bbox[1])
        rows: list[list[OCRResult]] = []
        current: list[OCRResult] = []
        current_y: Optional[float] = None

        for r in ordered:
            box = r.normalised_bbox
            y_center = (box[1] + box[3]) / 2
            if current_y is None or abs(y_center - current_y) <= tolerance:
                current.append(r)
                ys = [(x.normalised_bbox[1] + x.normalised_bbox[3]) / 2 for x in current]
                current_y = sum(ys) / len(ys)
            else:
                rows.append(sorted(current, key=lambda x: x.normalised_bbox[0]))
                current = [r]
                current_y = y_center

        if current:
            rows.append(sorted(current, key=lambda x: x.normalised_bbox[0]))
        return rows

    def to_reading_order_text(self, results: list[OCRResult]) -> str:
        """Render recognised regions as text in reading order."""
        return "\n".join(
            "  ".join(r.text for r in row) for row in self.group_into_lines(results)
        )
