"""SQLite database storage for analysis results and history."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.schemas import DocumentAnalysisResult

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite storage for engineering drawing analyses."""

    def __init__(self, db_path: str = settings.DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS analyses (
                    document_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    file_path TEXT,
                    total_pages INTEGER,
                    processing_started TEXT,
                    processing_completed TEXT,
                    total_processing_time_seconds REAL,
                    extraction_summary TEXT,
                    is_valid INTEGER,
                    issues_count INTEGER DEFAULT 0,
                    warnings_count INTEGER DEFAULT 0,
                    full_result TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS extracted_items (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    item_category TEXT,
                    page_number INTEGER,
                    value TEXT,
                    confidence REAL,
                    source_type TEXT,
                    bounding_box TEXT,
                    full_data TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES analyses(document_id)
                );

                CREATE TABLE IF NOT EXISTS detected_issues (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    issue_type TEXT,
                    severity TEXT,
                    description TEXT,
                    page_number INTEGER,
                    recommendation TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES analyses(document_id)
                );

                CREATE INDEX IF NOT EXISTS idx_items_doc ON extracted_items(document_id);
                CREATE INDEX IF NOT EXISTS idx_items_category ON extracted_items(item_category);
                CREATE INDEX IF NOT EXISTS idx_issues_doc ON detected_issues(document_id);
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save_analysis(self, result: DocumentAnalysisResult) -> None:
        """Persist full analysis result to database."""
        result.build_summary()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO analyses
                   (document_id, filename, file_path, total_pages,
                    processing_started, processing_completed,
                    total_processing_time_seconds, extraction_summary,
                    is_valid, issues_count, warnings_count, full_result)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.document_id,
                    result.filename,
                    result.file_path,
                    result.total_pages,
                    result.processing_started.isoformat(),
                    result.processing_completed.isoformat() if result.processing_completed else None,
                    result.total_processing_time_seconds,
                    json.dumps(result.extraction_summary),
                    1 if (result.validation_result and result.validation_result.is_valid) else 0,
                    len(result.all_issues),
                    len(result.validation_result.warnings) if result.validation_result else 0,
                    result.model_dump_json(),
                ),
            )

            # Save extracted items
            for pr in result.page_results:
                all_items = (
                    pr.dimensions + pr.tolerances + pr.holes + pr.welding_items
                    + pr.gd_t_items + pr.datums + pr.surface_finishes + pr.materials
                    + pr.manufacturing_notes + pr.bom_items + pr.section_views
                    + pr.detail_views + pr.critical_characteristics
                )
                for item in all_items:
                    conn.execute(
                        """INSERT INTO extracted_items
                           (id, document_id, item_category, page_number, value,
                            confidence, source_type, bounding_box, full_data)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            item.id,
                            result.document_id,
                            item.category.value,
                            item.page_number,
                            str(item.value),
                            item.confidence,
                            item.source_type.value,
                            json.dumps(item.bounding_box) if item.bounding_box else None,
                            item.model_dump_json(),
                        ),
                    )

            # Save issues
            for issue in result.all_issues:
                conn.execute(
                    """INSERT INTO detected_issues
                       (id, document_id, issue_type, severity, description,
                        page_number, recommendation)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        issue.id,
                        result.document_id,
                        issue.issue_type.value,
                        issue.severity.value,
                        issue.description,
                        issue.page_number,
                        issue.recommendation,
                    ),
                )

        logger.info("Saved analysis %s to database", result.document_id)

    def get_analysis(self, document_id: str) -> Optional[DocumentAnalysisResult]:
        """Retrieve a full analysis result by document ID."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT full_result FROM analyses WHERE document_id = ?",
                (document_id,),
            ).fetchone()
            if row:
                return DocumentAnalysisResult.model_validate_json(row["full_result"])
        return None

    def list_analyses(self, limit: int = 50) -> list[dict]:
        """List recent analyses with summary info."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT document_id, filename, total_pages,
                          processing_completed, extraction_summary,
                          is_valid, issues_count, warnings_count, created_at
                   FROM analyses ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_analysis(self, document_id: str) -> bool:
        with self._conn() as conn:
            conn.execute("DELETE FROM extracted_items WHERE document_id = ?", (document_id,))
            conn.execute("DELETE FROM detected_issues WHERE document_id = ?", (document_id,))
            cursor = conn.execute("DELETE FROM analyses WHERE document_id = ?", (document_id,))
            return cursor.rowcount > 0
