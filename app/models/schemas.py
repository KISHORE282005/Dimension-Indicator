"""Pydantic schemas for all extracted engineering data.

Every schema follows strict traceability: value, category, page, confidence,
bounding-box, and source reference are mandatory on every extracted item.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ExtractionCategory(str, Enum):
    DRAWING_INFO = "drawing_info"
    COMPONENT = "component"
    BOM = "bom"
    DIMENSION = "dimension"
    TOLERANCE = "tolerance"
    HOLE = "hole"
    WELDING = "welding"
    GD_T = "gd_t"
    DATUM = "datum"
    SURFACE_FINISH = "surface_finish"
    MATERIAL = "material"
    MANUFACTURING_NOTE = "manufacturing_note"
    SECTION_VIEW = "section_view"
    DETAIL_VIEW = "detail_view"
    CRITICAL_CHARACTERISTIC = "critical_characteristic"
    ANNOTATION = "annotation"
    TITLE_BLOCK = "title_block"
    REVISION = "revision"


class SeverityLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class SourceType(str, Enum):
    OCR = "ocr"
    VLM = "vlm"
    DETERMINISTIC = "deterministic"
    HYBRID = "hybrid"
    USER = "user"


class IssueType(str, Enum):
    MISSING_TOLERANCE = "missing_tolerance"
    DIMENSION_OUT_OF_RANGE = "dimension_out_of_range"
    INCONSISTENT_VALUES = "inconsistent_values"
    MISSING_MATERIAL = "missing_material"
    MISSING_DATUM = "missing_datum"
    GD_T_VIOLATION = "gd_t_violation"
    WELDING_CONFLICT = "welding_conflict"
    LOW_CONFIDENCE = "low_confidence"
    UNVERIFIED = "unverified"
    CALCULATION_MISMATCH = "calculation_mismatch"
    MISSING_NOTE = "missing_note"


# ---------------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------------

class BaseExtractedItem(BaseModel):
    """Every extracted piece of information inherits from this base."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    value: Any
    category: ExtractionCategory
    page_number: int
    confidence: float = Field(ge=0.0, le=1.0)
    bounding_box: Optional[list[float]] = Field(
        default=None,
        description="[x_min, y_min, x_max, y_max] normalised 0-1",
    )
    source_text: Optional[str] = None
    source_type: SourceType = SourceType.DETERMINISTIC
    extracted_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Drawing-level information
# ---------------------------------------------------------------------------

class DrawingMetadata(BaseExtractedItem):
    category: ExtractionCategory = ExtractionCategory.DRAWING_INFO
    drawing_number: Optional[str] = None
    revision: Optional[str] = None
    title: Optional[str] = None
    sheet_size: Optional[str] = None
    scale: Optional[str] = None
    drawn_by: Optional[str] = None
    checked_by: Optional[str] = None
    approved_by: Optional[str] = None
    date: Optional[str] = None
    company: Optional[str] = None
    drawing_standard: Optional[str] = None


# ---------------------------------------------------------------------------
# BOM / Parts
# ---------------------------------------------------------------------------

class BOMItem(BaseExtractedItem):
    category: ExtractionCategory = ExtractionCategory.BOM
    part_number: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[int] = None
    material: Optional[str] = None
    weight: Optional[str] = None
    remarks: Optional[str] = None
    row_index: Optional[int] = None


# ---------------------------------------------------------------------------
# Dimensions & Tolerances
# ---------------------------------------------------------------------------

class CriticalityLevel(str, Enum):
    CRITICAL = "Critical"
    NON_CRITICAL = "Non-Critical"


class ModeOfControl(str, Enum):
    CNC = "CNC"
    MANUAL = "Manual"
    CMM = "CMM"
    VISUAL = "Visual"
    GAUGE = "Gauge"
    AUTO = "Auto"
    NOT_DEFINED = "Not Defined"


class ModeOfInspection(str, Enum):
    FIRSTArticle = "First Article"
    IN_PROCESS = "In-Process"
    FINAL = "Final"
    SAMPLING = "Sampling"
    CMM = "CMM"
    GO_NOGO = "Go/No-Go"
    VISUAL = "Visual"
    NOT_DEFINED = "Not Defined"


class DimensionItem(BaseExtractedItem):
    category: ExtractionCategory = ExtractionCategory.DIMENSION
    dimension_number: Optional[int] = None
    dimension_type: Optional[str] = None  # linear, angular, radial, diameter
    nominal_value: Optional[float] = None
    unit: Optional[str] = None
    upper_limit: Optional[float] = None
    lower_limit: Optional[float] = None
    tolerance_value: Optional[float] = None
    specification: Optional[str] = None
    is_baseline: bool = False
    reference_only: bool = False
    leader_text: Optional[str] = None
    criticality: CriticalityLevel = CriticalityLevel.NON_CRITICAL
    mode_of_control: ModeOfControl = ModeOfControl.NOT_DEFINED
    mode_of_inspection: ModeOfInspection = ModeOfInspection.NOT_DEFINED


class ToleranceItem(BaseExtractedItem):
    category: ExtractionCategory = ExtractionCategory.TOLERANCE
    dimension_number: Optional[int] = None
    dimension_ref: Optional[str] = None
    nominal_value: Optional[float] = None
    upper_tolerance: Optional[float] = None
    lower_tolerance: Optional[float] = None
    upper_limit: Optional[float] = None
    lower_limit: Optional[float] = None
    fit_class: Optional[str] = None  # e.g. H7, g6
    tolerance_zone: Optional[str] = None
    unit: Optional[str] = None
    specification: Optional[str] = None
    criticality: CriticalityLevel = CriticalityLevel.NON_CRITICAL
    mode_of_control: ModeOfControl = ModeOfControl.NOT_DEFINED
    mode_of_inspection: ModeOfInspection = ModeOfInspection.NOT_DEFINED


# ---------------------------------------------------------------------------
# Holes
# ---------------------------------------------------------------------------

class HoleItem(BaseExtractedItem):
    category: ExtractionCategory = ExtractionCategory.HOLE
    dimension_number: Optional[int] = None
    hole_type: Optional[str] = None  # through, blind, countersink, counterbore, tapped
    diameter: Optional[float] = None
    depth: Optional[float] = None
    thread_spec: Optional[str] = None
    quantity: Optional[int] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    counterbore_diameter: Optional[float] = None
    countersink_angle: Optional[float] = None
    surface_finish_req: Optional[str] = None
    specification: Optional[str] = None
    criticality: CriticalityLevel = CriticalityLevel.NON_CRITICAL
    mode_of_control: ModeOfControl = ModeOfControl.NOT_DEFINED
    mode_of_inspection: ModeOfInspection = ModeOfInspection.NOT_DEFINED


# ---------------------------------------------------------------------------
# Welding
# ---------------------------------------------------------------------------

class WeldingItem(BaseExtractedItem):
    category: ExtractionCategory = ExtractionCategory.WELDING
    weld_type: Optional[str] = None  # fillet, groove, plug, slot, spot, seam
    weld_size: Optional[str] = None
    weld_length: Optional[str] = None
    joint_type: Optional[str] = None  # butt, corner, edge, lap, tee
    arrow_side: bool = False
    other_side: bool = False
    contour: Optional[str] = None  # flat, convex, concave
    finish_symbol: Optional[str] = None
    field_weld: bool = False
    weld_all_around: bool = False
    reference_standard: Optional[str] = None
    position: Optional[str] = None


# ---------------------------------------------------------------------------
# GD&T
# ---------------------------------------------------------------------------

class GDTItem(BaseExtractedItem):
    category: ExtractionCategory = ExtractionCategory.GD_T
    characteristic: Optional[str] = None  # flatness, position, runout, etc.
    symbol: Optional[str] = None
    tolerance_value: Optional[float] = None
    tolerance_zone_shape: Optional[str] = None  # cylindrical, planar, spherical
    modifier: Optional[str] = None  # MMC, LMC, RFS
    datum_references: list[str] = Field(default_factory=list)
    primary_datum: Optional[str] = None
    secondary_datum: Optional[str] = None
    tertiary_datum: Optional[str] = None
    feature_control_frame: Optional[str] = None
    applies_to: Optional[str] = None  # which feature the FCF applies to


class DatumItem(BaseExtractedItem):
    category: ExtractionCategory = ExtractionCategory.DATUM
    datum_label: Optional[str] = None  # A, B, C, etc.
    datum_type: Optional[str] = None  # plane, axis, point, center-plane
    feature_description: Optional[str] = None
    datum_reference_frame: Optional[str] = None


# ---------------------------------------------------------------------------
# Surface finish
# ---------------------------------------------------------------------------

class SurfaceFinishItem(BaseExtractedItem):
    category: ExtractionCategory = ExtractionCategory.SURFACE_FINISH
    roughness_value: Optional[float] = None
    roughness_unit: Optional[str] = "Ra"
    surface_method: Optional[str] = None  # machined, ground, turned, etc.
    lay_symbol: Optional[str] = None
    sampling_length: Optional[str] = None
    original_specification: Optional[str] = None


# ---------------------------------------------------------------------------
# Material
# ---------------------------------------------------------------------------

class MaterialItem(BaseExtractedItem):
    category: ExtractionCategory = ExtractionCategory.MATERIAL
    material_spec: Optional[str] = None
    material_name: Optional[str] = None
    material_grade: Optional[str] = None
    condition: Optional[str] = None  # annealed, hardened, etc.
    standard: Optional[str] = None  # ASTM, ISO, DIN


# ---------------------------------------------------------------------------
# Manufacturing notes
# ---------------------------------------------------------------------------

class ManufacturingNote(BaseExtractedItem):
    category: ExtractionCategory = ExtractionCategory.MANUFACTURING_NOTE
    note_number: Optional[int] = None
    note_text: str = ""
    note_type: Optional[str] = None  # general, finish, heat-treat, coating, tolerance_block


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class SectionView(BaseExtractedItem):
    category: ExtractionCategory = ExtractionCategory.SECTION_VIEW
    section_label: Optional[str] = None  # A-A, B-B
    cut_line: Optional[str] = None
    view_direction: Optional[str] = None
    parent_view: Optional[str] = None


class DetailView(BaseExtractedItem):
    category: ExtractionCategory = ExtractionCategory.DETAIL_VIEW
    detail_label: Optional[str] = None  # Detail A, Detail B
    scale: Optional[str] = None
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Critical characteristics
# ---------------------------------------------------------------------------

class CriticalCharacteristic(BaseExtractedItem):
    category: ExtractionCategory = ExtractionCategory.CRITICAL_CHARACTERISTIC
    characteristic_type: Optional[str] = None  # safety, functional, regulatory
    symbol: Optional[str] = None
    specification: Optional[str] = None
    feature_ref: Optional[str] = None


# ---------------------------------------------------------------------------
# Issues / warnings
# ---------------------------------------------------------------------------

class DetectedIssue(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    issue_type: IssueType
    severity: SeverityLevel
    description: str
    affected_items: list[str] = Field(default_factory=list)
    page_number: Optional[int] = None
    recommendation: Optional[str] = None
    extracted_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

class ValidationResult(BaseModel):
    is_valid: bool
    issues: list[DetectedIssue] = Field(default_factory=list)
    warnings: list[DetectedIssue] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=datetime.utcnow)
    rules_applied: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# AI interpretation (VLM output, clearly separated)
# ---------------------------------------------------------------------------

class AIInterpretation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_type: SourceType = SourceType.VLM
    page_number: int
    interpretation_text: str
    extracted_items: list[BaseExtractedItem] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    model_used: str = ""
    prompt_used: Optional[str] = None
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    disclaimer: str = (
        "This output was generated by an AI model and has NOT been independently "
        "verified. Treat as interpretation, not as extracted fact."
    )


# ---------------------------------------------------------------------------
# Consolidated dimension control list (report format)
# ---------------------------------------------------------------------------

class DimensionControlRow(BaseModel):
    """Single row in the engineering dimension control report."""
    dimension_number: int
    specification: str
    criticality: str = "Non-Critical"
    mode_of_control: str = "Not Defined"
    mode_of_inspection: str = "Not Defined"
    nominal_value: Optional[float] = None
    upper_limit: Optional[float] = None
    lower_limit: Optional[float] = None
    tolerance_value: Optional[float] = None
    unit: Optional[str] = None
    page_number: Optional[int] = None
    source_type: str = "deterministic"
    confidence: float = 0.0
    category: str = ""  # dimension, tolerance, hole
    original_id: str = ""


# ---------------------------------------------------------------------------
# Page-level processing result
# ---------------------------------------------------------------------------

class PageResult(BaseModel):
    page_number: int
    page_width: float
    page_height: float
    drawing_metadata: Optional[DrawingMetadata] = None
    bom_items: list[BOMItem] = Field(default_factory=list)
    dimensions: list[DimensionItem] = Field(default_factory=list)
    tolerances: list[ToleranceItem] = Field(default_factory=list)
    holes: list[HoleItem] = Field(default_factory=list)
    welding_items: list[WeldingItem] = Field(default_factory=list)
    gd_t_items: list[GDTItem] = Field(default_factory=list)
    datums: list[DatumItem] = Field(default_factory=list)
    surface_finishes: list[SurfaceFinishItem] = Field(default_factory=list)
    materials: list[MaterialItem] = Field(default_factory=list)
    manufacturing_notes: list[ManufacturingNote] = Field(default_factory=list)
    section_views: list[SectionView] = Field(default_factory=list)
    detail_views: list[DetailView] = Field(default_factory=list)
    critical_characteristics: list[CriticalCharacteristic] = Field(default_factory=list)
    other_annotations: list[BaseExtractedItem] = Field(default_factory=list)
    ai_interpretations: list[AIInterpretation] = Field(default_factory=list)
    dimension_control_list: list[DimensionControlRow] = Field(default_factory=list)
    processing_time_seconds: float = 0.0

    def build_dimension_control_list(self) -> list[DimensionControlRow]:
        """Build the consolidated dimension control report rows."""
        rows: list[DimensionControlRow] = []
        seq = 1

        for dim in self.dimensions:
            spec = dim.specification or str(dim.value)
            if dim.nominal_value is not None:
                spec = f"{dim.nominal_value}"
                if dim.tolerance_value is not None:
                    spec += f" +/- {dim.tolerance_value}"
                elif dim.upper_limit is not None and dim.lower_limit is not None:
                    spec += f" ({dim.lower_limit} to {dim.upper_limit})"
                if dim.unit:
                    spec += f" {dim.unit}"
            rows.append(DimensionControlRow(
                dimension_number=seq,
                specification=spec,
                criticality=dim.criticality.value,
                mode_of_control=dim.mode_of_control.value,
                mode_of_inspection=dim.mode_of_inspection.value,
                nominal_value=dim.nominal_value,
                upper_limit=dim.upper_limit,
                lower_limit=dim.lower_limit,
                tolerance_value=dim.tolerance_value,
                unit=dim.unit,
                page_number=dim.page_number,
                source_type=dim.source_type.value if hasattr(dim.source_type, 'value') else str(dim.source_type),
                confidence=dim.confidence,
                category="Dimension",
                original_id=dim.id,
            ))
            seq += 1

        for tol in self.tolerances:
            spec = tol.specification or str(tol.value)
            if tol.nominal_value is not None:
                spec = f"{tol.nominal_value}"
                if tol.upper_tolerance is not None and tol.lower_tolerance is not None:
                    spec += f" +{tol.upper_tolerance}/{tol.lower_tolerance}"
                elif tol.upper_limit is not None and tol.lower_limit is not None:
                    spec += f" ({tol.lower_limit} to {tol.upper_limit})"
                if tol.unit:
                    spec += f" {tol.unit}"
            rows.append(DimensionControlRow(
                dimension_number=seq,
                specification=spec,
                criticality=tol.criticality.value,
                mode_of_control=tol.mode_of_control.value,
                mode_of_inspection=tol.mode_of_inspection.value,
                nominal_value=tol.nominal_value,
                upper_limit=tol.upper_limit,
                lower_limit=tol.lower_limit,
                tolerance_value=tol.upper_tolerance,
                unit=tol.unit,
                page_number=tol.page_number,
                source_type=tol.source_type.value if hasattr(tol.source_type, 'value') else str(tol.source_type),
                confidence=tol.confidence,
                category="Tolerance",
                original_id=tol.id,
            ))
            seq += 1

        for hole in self.holes:
            spec = hole.specification or str(hole.value)
            if hole.diameter is not None:
                spec = f"Ø{hole.diameter}"
                if hole.depth is not None:
                    spec += f" x {hole.depth} deep"
                if hole.thread_spec:
                    spec += f" ({hole.thread_spec})"
                if hole.quantity and hole.quantity > 1:
                    spec += f" x{hole.quantity}"
            rows.append(DimensionControlRow(
                dimension_number=seq,
                specification=spec,
                criticality=hole.criticality.value,
                mode_of_control=hole.mode_of_control.value,
                mode_of_inspection=hole.mode_of_inspection.value,
                nominal_value=hole.diameter,
                unit="mm",
                page_number=hole.page_number,
                source_type=hole.source_type.value if hasattr(hole.source_type, 'value') else str(hole.source_type),
                confidence=hole.confidence,
                category="Hole",
                original_id=hole.id,
            ))
            seq += 1

        self.dimension_control_list = rows
        return rows


# ---------------------------------------------------------------------------
# Full document analysis result
# ---------------------------------------------------------------------------

class DocumentAnalysisResult(BaseModel):
    document_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    file_path: str
    total_pages: int
    file_size_bytes: Optional[int] = None
    processing_started: datetime = Field(default_factory=datetime.utcnow)
    processing_completed: Optional[datetime] = None
    total_processing_time_seconds: float = 0.0
    page_results: list[PageResult] = Field(default_factory=list)
    validation_result: Optional[ValidationResult] = None
    all_issues: list[DetectedIssue] = Field(default_factory=list)
    ai_interpretations_global: list[AIInterpretation] = Field(default_factory=list)
    extraction_summary: dict[str, int] = Field(default_factory=dict)
    consolidated_dimension_control: list[DimensionControlRow] = Field(default_factory=list)

    def build_summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for pr in self.page_results:
            for field_name in [
                "dimensions", "tolerances", "holes", "welding_items",
                "gd_t_items", "datums", "surface_finishes", "materials",
                "manufacturing_notes", "bom_items", "section_views",
                "detail_views", "critical_characteristics",
            ]:
                items = getattr(pr, field_name, [])
                counts[field_name] = counts.get(field_name, 0) + len(items)
        self.extraction_summary = counts
        return counts

    def build_consolidated_dimension_control(self) -> list[DimensionControlRow]:
        """Build the full consolidated dimension control list across all pages."""
        all_rows: list[DimensionControlRow] = []
        seq = 1
        for pr in self.page_results:
            pr.build_dimension_control_list()
            for row in pr.dimension_control_list:
                row.dimension_number = seq
                all_rows.append(row)
                seq += 1
        self.consolidated_dimension_control = all_rows
        return all_rows
