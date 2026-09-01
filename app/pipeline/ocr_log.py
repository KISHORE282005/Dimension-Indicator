"""Structured, file-based OCR debug logging.

In a deployed environment the console often cannot be reached, so when an OCR
problem shows up there is no way to see what PaddleOCR actually returned. This
module writes a complete, human-readable JSON log for every analysis run,
capturing:

* the OCR engine configuration and which text source was used,
* for each page: the raw detector output, every region kept (text, confidence,
  bounding box) and the reading-order text that was passed downstream,
* summary timing so a slow page is easy to spot.

The log is written as a single file at ``logs/jobs/<job_id>.ocr.json`` (or
``logs/jobs/datetime-<random>.ocr.json`` when no job id is known). Old finished
logs are pruned so the directory cannot grow without bound.

Use :class:`OCRRunLog` as a context manager around a pipeline run::

    with OCRRunLog(document_id="...") as run:
        run.setup(engine_name="paddleocr-3", ...)
        run.add_page_text(1, "reading order text")
        run.add_ocr_page(1, raw=..., kept=...)
    # on exit the JSON file is written
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _sanitise(name: str) -> str:
    return _SAFE.sub("_", name or "unknown")[:80] or "unknown"


class OCRRunLog:
    """Collects and writes a complete OCR debug log for one analysis run."""

    def __init__(
        self,
        document_id: str = "",
        job_id: str = "",
        filename: str = "",
        enabled: Optional[bool] = None,
    ) -> None:
        self.enabled = settings.OCR_DEBUG_LOG if enabled is None else enabled
        self.document_id = document_id or ""
        self.filename = filename or document_id or ""
        self._path: Optional[Path] = None
        self._payload: dict[str, Any] = {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "document_id": document_id,
            "job_id": job_id,
            "filename": filename,
            "ocr_engine": "unknown",
            "ocr_lang": settings.OCR_LANG,
            "ocr_max_image_size": settings.OCR_MAX_IMAGE_SIZE,
            "ocr_use_gpu": settings.OCR_USE_GPU,
            "notes": [],
            "pages": [],
            "summary": {},
        }
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "OCRRunLog":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._finalise()

    # ------------------------------------------------------------------
    # Configuration / setup
    # ------------------------------------------------------------------

    def setup(self, **fields: Any) -> None:
        with self._lock:
            self._payload.update(fields)

    def add_note(self, message: str) -> None:
        with self._lock:
            self._payload["notes"].append(
                {"at": datetime.utcnow().isoformat() + "Z", "message": message}
            )

    # ------------------------------------------------------------------
    # Per-page capture
    # ------------------------------------------------------------------

    def add_ocr_page(
        self,
        page_number: int,
        *,
        raw: Any = None,
        kept: list[Any] = None,
        dropped: int = 0,
        engine: str = "",
        elapsed_seconds: float = 0.0,
        note: str = "",
    ) -> None:
        """Record the raw detector output and the regions kept for one page."""
        with self._lock:
            self._payload["pages"].append(
                {
                    "page_number": page_number,
                    "engine": engine or self._payload.get("ocr_engine", ""),
                    "elapsed_seconds": round(elapsed_seconds, 4),
                    "note": note,
                    "raw_output": _jsonable(raw),
                    "kept_regions": [_jsonable(r) for r in (kept or [])],
                    "kept_count": len(kept or []),
                    "dropped_count": dropped,
                }
            )

    def add_page_text(
        self, page_number: int, text: str, *, source: str = "ocr"
    ) -> None:
        """Record the exact reading-order text handed to the downstream VLM."""
        with self._lock:
            self._payload["pages"].append(
                {
                    "page_number": page_number,
                    "source": source,
                    "reading_order_text": text or "",
                    "char_count": len(text or ""),
                }
            )

    # ------------------------------------------------------------------
    # Finalisation
    # ------------------------------------------------------------------

    def _finalise(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._payload["summary"] = {
                "page_count": len(
                    {
                        p["page_number"]
                        for p in self._payload["pages"]
                        if "page_number" in p
                    }
                ),
                "total_regions": sum(
                    p.get("kept_count", 0)
                    for p in self._payload["pages"]
                    if p.get("kept_count") is not None
                ),
                "total_dropped": sum(
                    p.get("dropped_count", 0)
                    for p in self._payload["pages"]
                    if p.get("dropped_count") is not None
                ),
                "notes": len(self._payload["notes"]),
            }
        path = self._write()
        if path:
            logger.info("Wrote OCR debug log: %s", path)

    def _write(self) -> Optional[Path]:
        if not self.enabled:
            return None
        try:
            if not self._path:
                self._path = self._default_path()
            self._path.write_text(
                json.dumps(self._payload, indent=2, default=_default), encoding="utf-8"
            )
            self._prune()
            return self._path
        except Exception as e:
            logger.warning("Could not write OCR debug log: %s", e)
            return None

    def _default_path(self) -> Path:
        stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        token = _sanitise(self.job_token())
        return Path(settings.LOG_DIR) / "jobs" / f"{stamp}-{token}.ocr.json"

    def job_token(self) -> str:
        return self._payload.get("job_id") or self.document_id or self.filename

    def _prune(self) -> None:
        keep = max(int(settings.OCR_DEBUG_LOG_KEEP), 1)
        try:
            log_dir = Path(settings.LOG_DIR) / "jobs"
            if not log_dir.is_dir():
                return
            files = sorted(log_dir.glob("*.ocr.json"), key=lambda p: p.stat().st_mtime)
            for old in files[:-keep]:
                old.unlink(missing_ok=True)
        except Exception as e:
            logger.debug("Could not prune OCR logs: %s", e)


def _jsonable(value: Any) -> Any:
    """Coerce a value so :func:`json.dumps` can serialize it safely."""
    if value is None:
        return None
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return value.tolist()
    except Exception:
        pass
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return "<bytes>"
    return _default(value)


def _default(value: Any) -> str:
    try:
        return str(value)
    except Exception:
        return "<?>"
