"""Main entry point for the Engineering Drawing Analysis System."""

import logging
import uvicorn
from app.config import settings
from app.backend.api import app

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main():
    print(f"\n{'='*60}")
    print(f"  {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"  API: http://{settings.API_HOST}:{settings.API_PORT}/docs")
    print(f"  Frontend: http://localhost:{settings.STREAMLIT_PORT}")
    print(f"{'='*60}\n")
    uvicorn.run(
        "app.backend.api:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )


if __name__ == "__main__":
    main()
