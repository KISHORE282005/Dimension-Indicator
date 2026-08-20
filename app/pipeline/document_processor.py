"""PDF and image processing module using PyMuPDF and OpenCV.

Handles rendering PDF pages to images, image preprocessing (grayscale,
threshold, sharpen, denoise), and region extraction for OCR.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Optional

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)


class ProcessedPage:
    """Container for a single processed page."""

    def __init__(
        self,
        page_number: int,
        original_image: np.ndarray,
        processed_image: np.ndarray,
        width: int,
        height: int,
        dpi: float,
        text_blocks: Optional[list[dict]] = None,
    ) -> None:
        self.page_number = page_number
        self.original_image = original_image
        self.processed_image = processed_image
        self.width = width
        self.height = height
        self.dpi = dpi
        self.text_blocks = text_blocks or []

    def to_pil(self) -> Image.Image:
        rgb = cv2.cvtColor(self.processed_image, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

    def to_bytes(self, fmt: str = "PNG") -> bytes:
        pil = self.to_pil()
        buf = io.BytesIO()
        pil.save(buf, format=fmt)
        return buf.getvalue()


class DocumentProcessor:
    """Process PDF files and images into preprocessed page images."""

    def __init__(
        self,
        dpi: int = settings.PDF_RENDER_DPI,
        max_size: int = settings.MAX_IMAGE_SIZE,
    ) -> None:
        self.dpi = dpi
        self.max_size = max_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_file(self, file_path: str | Path) -> list[ProcessedPage]:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            return self._process_pdf(file_path)
        if suffix in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}:
            return self._process_image(file_path)
        raise ValueError(f"Unsupported file type: {suffix}")

    # ------------------------------------------------------------------
    # PDF processing
    # ------------------------------------------------------------------

    def _process_pdf(self, path: Path) -> list[ProcessedPage]:
        doc = fitz.open(str(path))
        pages: list[ProcessedPage] = []
        zoom = self.dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        for idx in range(len(doc)):
            page = doc[idx]
            # Render to pixmap
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            if pix.n == 4:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
            else:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

            processed = self._preprocess_image(img_array)

            # Extract text blocks with positions
            text_blocks = []
            for block in page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]:
                if block.get("type") == 0:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text_blocks.append({
                                "text": span.get("text", ""),
                                "bbox": span.get("bbox", []),
                                "font": span.get("font", ""),
                                "size": span.get("size", 0),
                            })

            pages.append(
                ProcessedPage(
                    page_number=idx + 1,
                    original_image=img_array,
                    processed_image=processed,
                    width=pix.width,
                    height=pix.height,
                    dpi=self.dpi,
                    text_blocks=text_blocks,
                )
            )
            logger.info("Rendered page %d (%dx%d)", idx + 1, pix.width, pix.height)

        doc.close()
        return pages

    # ------------------------------------------------------------------
    # Image processing
    # ------------------------------------------------------------------

    def _process_image(self, path: Path) -> list[ProcessedPage]:
        img = cv2.imread(str(path))
        if img is None:
            raise ValueError(f"Cannot read image: {path}")

        img = self._resize_if_needed(img)
        processed = self._preprocess_image(img)
        h, w = img.shape[:2]
        return [
            ProcessedPage(
                page_number=1,
                original_image=img,
                processed_image=processed,
                width=w,
                height=h,
                dpi=96.0,
            )
        ]

    # ------------------------------------------------------------------
    # Image preprocessing (OpenCV)
    # ------------------------------------------------------------------

    def _preprocess_image(self, img: np.ndarray) -> np.ndarray:
        """Full preprocessing pipeline: grayscale, denoise, sharpen, threshold."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray, h=10)
        sharpened = self._sharpen(denoised)
        binary = self._adaptive_threshold(sharpened)
        # Convert back to 3-channel for downstream consumers
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    @staticmethod
    def _sharpen(gray: np.ndarray) -> np.ndarray:
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        return cv2.filter2D(gray, -1, kernel)

    @staticmethod
    def adaptive_threshold(gray: np.ndarray) -> np.ndarray:
        return cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 8,
        )

    def _adaptive_threshold(self, gray: np.ndarray) -> np.ndarray:
        return self.adaptive_threshold(gray)

    def _resize_if_needed(self, img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        if max(h, w) <= self.max_size:
            return img
        scale = self.max_size / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # ------------------------------------------------------------------
    # Region extraction
    # ------------------------------------------------------------------

    def extract_region(
        self,
        page: ProcessedPage,
        bbox: list[float],
        padding: int = 10,
    ) -> np.ndarray:
        """Extract a region from a page image using normalised bbox."""
        x_min, y_min, x_max, y_max = bbox
        h, w = page.processed_image.shape[:2]
        x1 = max(0, int(x_min * w) - padding)
        y1 = max(0, int(y_min * h) - padding)
        x2 = min(w, int(x_max * w) + padding)
        y2 = min(h, int(y_max * h) + padding)
        return page.processed_image[y1:y2, x1:x2]

    @staticmethod
    def to_base64(img: np.ndarray) -> str:
        import base64
        _, buffer = cv2.imencode(".png", img)
        return base64.b64encode(buffer).decode("utf-8")
