"""Pipeline orchestrator — coordinates the full extraction pipeline.

Document Processing → OCR → VLM Reasoning → Rule Engine → Database → Reports
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Callable, Optional

from app.config import settings
from app.engine.rule_engine import EngineeringRuleEngine
from app.models.schemas import (
    AIInterpretation,
    BaseExtractedItem,
    BOMItem,
    DatumItem,
    DimensionItem,
    DrawingMetadata,
    ExtractionCategory,
    GDTItem,
    HoleItem,
    ManufacturingNote,
    MaterialItem,
    PageResult,
    SectionView,
    DetailView,
    CriticalCharacteristic,
    SurfaceFinishItem,
    WeldingItem,
    DocumentAnalysisResult,
)
from app.pipeline.document_processor import DocumentProcessor, ProcessedPage
from app.pipeline.ocr_engine import OCREngine
from app.pipeline.vlm_engine import VLMEngine

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Orchestrates the full engineering drawing analysis pipeline."""

    def __init__(self) -> None:
        self.doc_processor = DocumentProcessor()
        self.ocr_engine = OCREngine()
        self.vlm_engine = VLMEngine()
        self.rule_engine = EngineeringRuleEngine()
        self._progress_callback: Optional[Callable[[str, float], None]] = None

    def set_progress_callback(self, callback: Callable[[str, float], None]) -> None:
        self._progress_callback = callback

    def _report_progress(self, stage: str, pct: float) -> None:
        if self._progress_callback:
            self._progress_callback(stage, pct)
        logger.info("[%s] %.0f%%", stage, pct * 100)

    def analyze(
        self,
        file_path: str | Path,
        use_vlm: bool = True,
        ocr_min_confidence: float = 0.3,
    ) -> DocumentAnalysisResult:
        """Run the full analysis pipeline on a document."""
        file_path = Path(file_path)
        start_time = time.time()

        result = DocumentAnalysisResult(
            filename=file_path.name,
            file_path=str(file_path),
            total_pages=0,
        )

        # Stage 1: Document processing
        self._report_progress("processing", 0.0)
        try:
            pages = self.doc_processor.process_file(file_path)
        except Exception as e:
            logger.error("Document processing failed: %s", e)
            result.processing_completed = result.processing_started
            result.total_processing_time_seconds = time.time() - start_time
            return result

        result.total_pages = len(pages)
        self._report_progress("processing", 0.2)
        logger.info("Processed %d pages from %s", len(pages), file_path.name)

        # Stage 2: OCR + VLM per page
        page_results: list[PageResult] = []
        for i, page in enumerate(pages):
            page_start = time.time()
            self._report_progress("ocr", 0.2 + 0.5 * (i / max(len(pages), 1)))

            # OCR
            ocr_results = self.ocr_engine.extract_text(
                page.processed_image,
                page_number=page.page_number,
                min_confidence=ocr_min_confidence,
            )
            ocr_text = "\n".join(r.text for r in ocr_results)

            # VLM analysis (if enabled and available)
            ai_interp = None
            if use_vlm and self.vlm_engine.is_available():
                self._report_progress("vlm", 0.2 + 0.5 * (i / max(len(pages), 1)))
                ai_interp = self.vlm_engine.analyze_page(
                    page.processed_image,
                    ocr_text,
                    page.page_number,
                )

            # Merge OCR and VLM results into structured PageResult
            pr = self._merge_results(
                page=page,
                ocr_results=ocr_results,
                ai_interp=ai_interp,
            )
            pr.processing_time_seconds = time.time() - page_start
            page_results.append(pr)

        result.page_results = page_results
        self._report_progress("validation", 0.75)

        # Stage 3: Deterministic validation
        result.validation_result = self.rule_engine.validate(page_results)
        result.all_issues = (
            result.validation_result.issues + result.validation_result.warnings
        )
        self._report_progress("validation", 0.9)

        # Stage 4: Build summary
        result.build_summary()
        result.build_consolidated_dimension_control()
        from datetime import datetime
        result.processing_completed = datetime.utcnow()
        result.total_processing_time_seconds = time.time() - start_time

        self._report_progress("complete", 1.0)
        logger.info(
            "Analysis complete: %d pages, summary=%s, %.1fs",
            result.total_pages,
            result.extraction_summary,
            result.total_processing_time_seconds,
        )

        return result

    def _merge_results(
        self,
        page: ProcessedPage,
        ocr_results: list,
        ai_interp: Optional[AIInterpretation],
    ) -> PageResult:
        """Merge OCR text blocks and VLM interpretations into a PageResult."""
        pr = PageResult(
            page_number=page.page_number,
            page_width=page.width,
            page_height=page.height,
        )

        # If VLM produced structured items, use them
        if ai_interp and ai_interp.extracted_items:
            pr.ai_interpretations = [ai_interp]
            for item in ai_interp.extracted_items:
                self._categorize_item(pr, item)

            # If VLM found drawing metadata, store it
            for item in ai_interp.extracted_items:
                if isinstance(item, DrawingMetadata):
                    pr.drawing_metadata = item
                    break

        # Supplement with OCR-extracted text blocks if VLM didn't find enough
        if not pr.dimensions and page.text_blocks:
            pr.other_annotations.extend(
                self._text_blocks_to_annotations(page.text_blocks, page.page_number)
            )

        return pr

    @staticmethod
    def _categorize_item(pr: PageResult, item: BaseExtractedItem) -> None:
        """Route an extracted item to the correct list in PageResult."""
        cat = item.category
        if cat == ExtractionCategory.DRAWING_INFO:
            if isinstance(item, DrawingMetadata):
                pr.drawing_metadata = item
        elif cat == ExtractionCategory.BOM and isinstance(item, BOMItem):
            pr.bom_items.append(item)
        elif cat == ExtractionCategory.DIMENSION and isinstance(item, DimensionItem):
            pr.dimensions.append(item)
        elif cat == ExtractionCategory.TOLERANCE and isinstance(item, ToleranceItem):
            pr.tolerances.append(item)
        elif cat == ExtractionCategory.HOLE and isinstance(item, HoleItem):
            pr.holes.append(item)
        elif cat == ExtractionCategory.WELDING and isinstance(item, WeldingItem):
            pr.welding_items.append(item)
        elif cat == ExtractionCategory.GD_T and isinstance(item, GDTItem):
            pr.gd_t_items.append(item)
        elif cat == ExtractionCategory.DATUM and isinstance(item, DatumItem):
            pr.datums.append(item)
        elif cat == ExtractionCategory.SURFACE_FINISH and isinstance(item, SurfaceFinishItem):
            pr.surface_finishes.append(item)
        elif cat == ExtractionCategory.MATERIAL and isinstance(item, MaterialItem):
            pr.materials.append(item)
        elif cat == ExtractionCategory.MANUFACTURING_NOTE and isinstance(item, ManufacturingNote):
            pr.manufacturing_notes.append(item)
        elif cat == ExtractionCategory.SECTION_VIEW and isinstance(item, SectionView):
            pr.section_views.append(item)
        elif cat == ExtractionCategory.DETAIL_VIEW and isinstance(item, DetailView):
            pr.detail_views.append(item)
        elif cat == ExtractionCategory.CRITICAL_CHARACTERISTIC and isinstance(item, CriticalCharacteristic):
            pr.critical_characteristics.append(item)
        else:
            pr.other_annotations.append(item)

    @staticmethod
    def _text_blocks_to_annotations(
        text_blocks: list[dict], page_number: int
    ) -> list[BaseExtractedItem]:
        """Convert raw OCR text blocks to generic annotation items."""
        annotations = []
        for block in text_blocks:
            text = block.get("text", "").strip()
            if not text:
                continue
            bbox = block.get("bbox", [])
            norm_bbox = None
            if len(bbox) == 4:
                norm_bbox = [bbox[0], bbox[1], bbox[2], bbox[3]]
            annotations.append(
                BaseExtractedItem(
                    value=text,
                    category=ExtractionCategory.ANNOTATION,
                    page_number=page_number,
                    confidence=0.5,
                    source_type="ocr",
                    bounding_box=norm_bbox,
                    source_text=text,
                )
            )
        return annotations
