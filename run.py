"""Main entry point for the Engineering Drawing Analysis System."""

import logging
from logging.handlers import RotatingFileHandler

import uvicorn

from app.config import settings

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def _configure_file_logging() -> None:
    """Mirror all application logs to a rotating file on disk.

    In a deployed environment the process is often daemonised and its console
    output is lost or rotated away by the supervisor, so a per-run OCR debug
    log alone is not enough to reconstruct a failure. This writes the standard
    module logs (OCR init, per-page counts, VLM/Gemini calls, pipeline stages,
    job failures) to ``logs/app.log`` with a rolling max of 10 x 5 MB.
    """
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = settings.LOG_DIR / "app.log"
    handler = RotatingFileHandler(
        str(log_file), maxBytes=5 * 1024 * 1024, backupCount=10, encoding="utf-8"
    )
    handler.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.addHandler(handler)


_configure_file_logging()

_PLACEHOLDER_KEYS = {"", "your_gemini_api_key_here", "your_api_key_here", "changeme", "none"}


def _key_configured() -> bool:
    return (settings.GEMINI_API_KEY or "").strip().lower() not in _PLACEHOLDER_KEYS


def _banner() -> None:
    host = "localhost" if settings.API_HOST in {"0.0.0.0", "127.0.0.1"} else settings.API_HOST
    print(f"\n{'=' * 64}")
    print(f"  {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"  Interface:  http://{host}:{settings.API_PORT}/")
    print(f"  API docs:   http://{host}:{settings.API_PORT}/docs")
    print(f"  Running at: {settings.API_URL}/")
    print(f"  Model:      {settings.GEMINI_MODEL}")

    if not _key_configured():
        print()
        print("  ! GEMINI_API_KEY is not set in .env")
        print("    The app will run, but nothing will be read from drawings -")
        print("    reports will contain only what you type.")
    print(f"{'=' * 64}\n")


def main() -> None:
    _banner()
    uvicorn.run(
        "app.backend.api:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.RELOAD,
        reload_excludes=(
            [
                "uploads",
                "uploads/*",
                "output",
                "output/*",
                "database",
                "database/*",
                ".git",
                ".git/*",
                "frontend/node_modules",
                "frontend/node_modules/*",
                "frontend/dist",
                "frontend/dist/*",
            ]
            if settings.RELOAD
            else None
        ),
        log_level="debug" if settings.DEBUG else "info",
    )


if __name__ == "__main__":
    main()
