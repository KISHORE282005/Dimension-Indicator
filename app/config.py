"""Application configuration management."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the engineering drawing analysis system."""

    APP_NAME: str = "Engineering Drawing Analysis System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    OUTPUT_DIR: Path = BASE_DIR / "output"
    MODELS_DIR: Path = BASE_DIR / "models"
    DATABASE_DIR: Path = BASE_DIR / "database"

    PDF_RENDER_DPI: int = 300
    MAX_IMAGE_SIZE: int = 4096
    OCR_LANG: str = "en"
    OCR_USE_GPU: bool = False
    OCR_DET_DB_THRESH: float = 0.3
    OCR_DET_DB_BOX_THRESH: float = 0.5

    GEMINI_MODEL: str = "gemini-2.5-pro"
    GEMINI_API_KEY: str = ""
    GEMINI_MAX_TOKENS: int = 8192
    GEMINI_TEMPERATURE: float = 0.1

    YOLO_MODEL_PATH: str = str(MODELS_DIR / "yolov11" / "best.pt")
    YOLO_CONFIDENCE_THRESHOLD: float = 0.5
    YOLO_ENABLE_CUSTOM: bool = False

    DB_PATH: str = str(DATABASE_DIR / "engineering_analysis.db")

    REPORT_LOGO_PATH: str = ""
    REPORT_COMPANY_NAME: str = "Engineering Analysis System"

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    STREAMLIT_PORT: int = 8501

    TOLERANCE_PRECISION: int = 4
    DIMENSION_CONFIDENCE_THRESHOLD: float = 0.4

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
    }


settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
settings.DATABASE_DIR.mkdir(parents=True, exist_ok=True)
