"""Deep deployment self-check.

Probes the OCR stack, Gemini key + model reachability, the frontend build,
writable runtime directories and environment configuration. Used by the
``/api/diagnostics`` endpoint and by ``python -m app.diagnostics`` so a
deployed server can be inspected instead of guessed at.

Every check returns the same shape:

.. code-block:: python

    {
        "name": "...",
        "status": "ok" | "warning" | "error",
        "verdict": "one-line human summary",
        "fix": "one-line remediation, or '' when nothing to fix",
    }

``run_diagnostics()`` returns that list.
"""

from __future__ import annotations

import importlib
import logging
import os
import shutil
import sys
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_log = logging.getLogger(__name__)


def _check_env() -> dict:
    """Verify required environment configuration is present."""
    missing = []
    optional = []
    for key in ("GEMINI_API_KEY",):
        if not getattr(settings, key, ""):
            missing.append(key)

    for key in ("GEMINI_MODEL", "OCR_LANG", "DB_PATH", "API_URL"):
        if not getattr(settings, key, ""):
            optional.append(key)

    if missing:
        verdict = "Missing env setting(s): " + ", ".join(missing)
        status = "error"
        fix = "Add them to the .env file and restart the server."
    elif optional:
        verdict = "Env present but one or more optional settings are empty: " + ", ".join(optional)
        status = "warning"
        fix = "Set any intentionally-empty optional settings in .env."
    else:
        verdict = "Environment configuration looks complete."
        status = "ok"
        fix = ""

    return {
        "name": "environment",
        "status": status,
        "verdict": verdict,
        "fix": fix,
    }


def _check_dirs() -> dict:
    """Verify all runtime directories exist and are writable."""
    problems = []
    for name, path in (
        ("uploads", settings.UPLOAD_DIR),
        ("output", settings.OUTPUT_DIR),
        ("database", settings.DATABASE_DIR),
        ("logs", settings.LOG_DIR),
        ("logs/jobs", settings.LOG_DIR / "jobs"),
    ):
        try:
            path = Path(path)
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            problems.append(f"{name} ({path}): {exc}")

    if problems:
        status = "error"
        verdict = "Writable-directory check failed:"
        fix = "; ".join(problems)
    else:
        status = "ok"
        verdict = "All runtime directories exist and are writable."
        fix = ""

    return {
        "name": "runtime_directories",
        "status": status,
        "verdict": verdict,
        "fix": fix,
    }


def _check_ocr() -> dict:
    """Probe the OCR stack; Paddle and friends are the first thing that
    breaks on a fresh or minimal deployment."""
    missing = []
    for mod in ("paddle", "paddleocr", "cv2"):
        try:
            importlib.import_module(mod)
        except Exception as exc:  # noqa: BLE001 - best-effort probe
            missing.append(f"{mod} ({type(exc).__name__})")

    if missing:
        status = "error"
        verdict = "OCR stack unavailable: " + ", ".join(missing)
        fix = "Install the OCR requirements (see requirements/ocr.txt)."
    else:
        status = "ok"
        verdict = "OCR stack (Paddle / PaddleOCR / OpenCV) is importable."
        fix = ""

    return {
        "name": "ocr_stack",
        "status": status,
        "verdict": verdict,
        "fix": fix,
    }


def _check_gemini() -> dict:
    """Verify a Gemini API key is configured and the model can be reached."""
    from app.pipeline.gemini_client import GeminiClient

    if not settings.GEMINI_API_KEY:
        return {
            "name": "gemini",
            "status": "error",
            "verdict": "GEMINI_API_KEY is not set; no model reachability check was run.",
            "fix": "Set GEMINI_API_KEY in .env and restart the server.",
        }

    client = GeminiClient()
    try:
        available = client.is_available()
    except Exception as exc:  # noqa: BLE001 - best-effort probe
        return {
            "name": "gemini",
            "status": "error",
            "verdict": f"Gemini reachability check errored: {exc}",
            "fix": "Check the API key and network access to Google AI.",
        }

    if available:
        return {
            "name": "gemini",
            "status": "ok",
            "verdict": f"Gemini ({settings.GEMINI_MODEL}) is reachable and the key is valid.",
            "fix": "",
        }

    return {
        "name": "gemini",
        "status": "error",
        "verdict": f"Gemini ({settings.GEMINI_MODEL}) could not be reached or the key is invalid.",
        "fix": "Validate GEMINI_API_KEY and that the model name is enabled for the project.",
    }


def _check_frontend() -> dict:
    """Verify the built frontend assets exist so the UI can be served."""
    frontend_candidates = [
        settings.BASE_DIR / "frontend" / "dist",
        settings.BASE_DIR / "static",
    ]
    index_files = [
        path / "index.html" for path in frontend_candidates if (path / "index.html").exists()
    ]

    if index_files:
        status = "ok"
        verdict = f"Frontend build present ({index_files[0]})."
        fix = ""
    else:
        status = "warning"
        verdict = "No built frontend (frontend/dist or static/index.html) found; API-only mode."
        fix = "Run the frontend build (npm run build) to serve the UI from this server."

    return {
        "name": "frontend_build",
        "status": status,
        "verdict": verdict,
        "fix": fix,
    }


_CHECKS = (
    _check_env,
    _check_dirs,
    _check_ocr,
    _check_gemini,
    _check_frontend,
)


def run_diagnostics() -> list[dict]:
    """Run every deployment self-check and return the results list."""
    return [check() for check in _CHECKS]


def main() -> int:
    """CLI entry point, equivalent to ``python -m app.diagnostics``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    results = run_diagnostics()
    for item in results:
        print(f"[{item['status'].upper():7s}] {item['name']}: {item['verdict']}")
        if item["fix"]:
            print(f"        FIX: {item['fix']}")

    bad = [r for r in results if r["status"] == "error"]
    print()
    print(f"{len(results) - len(bad)}/{len(results)} checks passed.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
