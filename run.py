"""Main entry point for the Engineering Drawing Analysis System."""

import logging

import uvicorn

from app.config import settings

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

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
