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
    """Container for a single processed page.

    Two renderings are kept deliberately:

    - ``original_image``  the clean render straight from the PDF. This is what
      the vision model sees. Binarising or sharpening a drawing before sending
      it to a VLM destroys thin extension lines, centre lines and light GD&T
      glyphs, which is exactly the detail the model is being asked to read.
    - ``processed_image``  contrast-normalised and binarised, which is what
      helps a classical OCR detector find text boxes.
    """

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

    def to_vlm_bytes(self, max_edge: int = 2048, fmt: str = "PNG") -> bytes:
        """Encode the clean render for a vision model.

        Downscaled with INTER_AREA so line work stays continuous, and capped so
        a 300 DPI A1 sheet does not blow past the request size limit.
        """
        img = self.original_image
        h, w = img.shape[:2]
        if max(h, w) > max_edge:
            scale = max_edge / max(h, w)
            img = cv2.resize(
                img, (max(int(w * scale), 1), max(int(h * scale), 1)),
                interpolation=cv2.INTER_AREA,
            )
        ext = ".png" if fmt.upper() == "PNG" else ".jpg"
        params = [] if ext == ".png" else [cv2.IMWRITE_JPEG_QUALITY, 92]
        ok, buf = cv2.imencode(ext, img, params)
        if not ok:
            raise ValueError(f"Failed to encode page {self.page_number} as {fmt}")
        return buf.tobytes()

    def has_text_layer(self) -> bool:
        """True when the PDF carries real vector text for this page."""
        return any(str(b.get("text", "")).strip() for b in self.text_blocks)


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
            elif pix.n == 1:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_GRAY2BGR)
            else:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

            # A 300 DPI A1 sheet renders to ~10000 px on the long edge. Cap it
            # before preprocessing or the filters take minutes per page.
            img_array = self._resize_if_needed(img_array)
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

            page_h, page_w = img_array.shape[:2]
            pages.append(
                ProcessedPage(
                    page_number=idx + 1,
                    original_image=img_array,
                    processed_image=processed,
                    width=page_w,
                    height=page_h,
                    dpi=self.dpi * (page_w / pix.width) if pix.width else self.dpi,
                    text_blocks=text_blocks,
                )
            )
            logger.info(
                "Rendered page %d/%d (%dx%d, %d text spans)",
                idx + 1,
                len(doc),
                page_w,
                page_h,
                len(text_blocks),
            )

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
        """Prepare a page for the OCR text detector.

        Tuned for line drawings rather than photographs of documents:

        - CLAHE lifts faint hand-added or low-contrast annotation text without
          also amplifying the paper texture across the whole sheet.
        - A 3x3 median removes speckle from scans while leaving 1 px drawing
          lines intact, unlike a Gaussian blur.
        - Adaptive threshold uses a 25 px window. The 15 px window used before
          is narrower than the stroke width of title-block text at 300 DPI, so
          it hollowed out thick glyphs into outlines.

        The previous chain also ran an unsharp kernel with a centre weight of 9
        before thresholding, which turned every drawing line into a black/white
        ringing pair and manufactured phantom text boxes for the detector.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        equalised = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        denoised = cv2.medianBlur(equalised, 3)
        binary = self._adaptive_threshold(denoised)
        # Downstream consumers (PaddleOCR, crops) expect 3-channel input.
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    @staticmethod
    def adaptive_threshold(gray: np.ndarray) -> np.ndarray:
        return cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 25, 10,
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
