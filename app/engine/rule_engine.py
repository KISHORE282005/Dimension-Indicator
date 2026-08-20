"""Deterministic Engineering Rule Engine.

Validates extracted engineering data using hard rules.
Never uses AI/LLM for validation — purely deterministic logic.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from app.models.schemas import (
    CriticalCharacteristic,
    CriticalityLevel,
    DetectedIssue,
    DimensionItem,
    ExtractionCategory,
    GDTItem,
    HoleItem,
    IssueType,
    MaterialItem,
    ModeOfControl,
    ModeOfInspection,
    PageResult,
    SeverityLevel,
    ToleranceItem,
    ValidationResult,
    WeldingItem,
)

logger = logging.getLogger(__name__)


class EngineeringRuleEngine:
    """Rule-based validation engine for engineering drawing data."""

    # Known material specs (subset for validation)
    KNOWN_MATERIAL_STANDARDS = {
        "ASTM", "AISI", "SAE", "DIN", "EN", "ISO", "JIS", "BS",
        "MIL", "AMS", "UNS", "GB",
    }

    # Common GD&T characteristics
    VALID_GD_T_CHARACTERISTICS = {
        "flatness", "straightness", "circularity", "cylindricity",
        "profile of a line", "profile of a surface", "angularity",
        "perpendicularity", "parallelism", "position", "concentricity",
        "symmetry", "circular runout", "total runout",
    }

    # Standard tolerance zones
    STANDARD_TOLERANCE_CLASSES = {
        "IT01", "IT0", "IT1", "IT2", "IT3", "IT4", "IT5", "IT6",
        "IT7", "IT8", "IT9", "IT10", "IT11", "IT12", "IT13",
        "IT14", "IT15", "IT16", "IT17", "IT18",
    }

    # Fit classes
    HOLE_BASE_FITS = {"H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10", "H11"}
    SHAFT_BASE_FITS = {"g3", "g4", "g5", "g6", "g7", "g8", "h3", "h4", "h5", "h6", "h7", "h8",
                       "k5", "k6", "k7", "m5", "m6", "m7", "n6", "n7", "p6", "p7", "s6", "s7"}

    def validate(self, page_results: list[PageResult]) -> ValidationResult:
        """Run all validation rules and classify dimensions across all pages."""
        issues: list[DetectedIssue] = []
        rules_applied: list[str] = []

        # --- Classify criticality and control/inspection modes ---
        self._classify_all(page_results)
        rules_applied.append("criticality_classification")

        # --- Build dimension control lists ---
        for pr in page_results:
            pr.build_dimension_control_list()
        rules_applied.append("dimension_control_list")

        # --- Dimension rules ---
        issues.extend(self._check_dimensions(page_results))
        rules_applied.append("dimension_validation")

        # --- Tolerance rules ---
        issues.extend(self._check_tolerances(page_results))
        rules_applied.append("tolerance_validation")

        # --- Hole rules ---
        issues.extend(self._check_holes(page_results))
        rules_applied.append("hole_validation")

        # --- GD&T rules ---
        issues.extend(self._check_gd_t(page_results))
        rules_applied.append("gd_t_validation")

        # --- Welding rules ---
        issues.extend(self._check_welding(page_results))
        rules_applied.append("welding_validation")

        # --- Material rules ---
        issues.extend(self._check_materials(page_results))
        rules_applied.append("material_validation")

        # --- Cross-page consistency ---
        issues.extend(self._check_cross_page_consistency(page_results))
        rules_applied.append("cross_page_consistency")

        # --- Missing information ---
        issues.extend(self._check_missing_information(page_results))
        rules_applied.append("missing_information")

        errors = [i for i in issues if i.severity in (SeverityLevel.ERROR, SeverityLevel.CRITICAL)]
        warnings = [i for i in issues if i.severity in (SeverityLevel.WARNING, SeverityLevel.INFO)]

        logger.info(
            "Validation complete: %d errors, %d warnings, %d rules applied",
            len(errors),
            len(warnings),
            len(rules_applied),
        )

        return ValidationResult(
            is_valid=len(errors) == 0,
            issues=errors,
            warnings=warnings,
            rules_applied=rules_applied,
        )

    # ------------------------------------------------------------------
    # Dimension rules
    # ------------------------------------------------------------------

    def _check_dimensions(self, pages: list[PageResult]) -> list[DetectedIssue]:
        issues: list[DetectedIssue] = []

        for page in pages:
            for dim in page.dimensions:
                # Check: nominal value exists
                if dim.nominal_value is None and dim.source_text:
                    try:
                        extracted = self._extract_numeric(dim.source_text or str(dim.value))
                        if extracted is not None:
                            issues.append(
                                DetectedIssue(
                                    issue_type=IssueType.INCONSISTENT_VALUES,
                                    severity=SeverityLevel.WARNING,
                                    description=(
                                        f"Dimension '{dim.value}' has no parsed nominal value "
                                        f"but source text contains a number."
                                    ),
                                    affected_items=[dim.id],
                                    page_number=page.page_number,
                                    recommendation="Manually verify dimension value.",
                                )
                            )
                    except (ValueError, TypeError):
                        pass

                # Check: negative values for linear dimensions
                if dim.nominal_value is not None and dim.nominal_value < 0:
                    if dim.dimension_type in (None, "linear", "diameter"):
                        issues.append(
                            DetectedIssue(
                                issue_type=IssueType.DIMENSION_OUT_OF_RANGE,
                                severity=SeverityLevel.WARNING,
                                description=(
                                    f"Negative linear dimension value: {dim.nominal_value}. "
                                    f"Verify if this is intentional."
                                ),
                                affected_items=[dim.id],
                                page_number=page.page_number,
                            )
                        )

                # Check: tolerance bounds consistency
                if dim.upper_limit is not None and dim.lower_limit is not None:
                    if dim.upper_limit < dim.lower_limit:
                        issues.append(
                            DetectedIssue(
                                issue_type=IssueType.INCONSISTENT_VALUES,
                                severity=SeverityLevel.ERROR,
                                description=(
                                    f"Upper limit ({dim.upper_limit}) < lower limit ({dim.lower_limit})."
                                ),
                                affected_items=[dim.id],
                                page_number=page.page_number,
                            )
                        )

                # Check: tolerance wider than 10% of nominal
                if (dim.nominal_value and dim.tolerance_value
                        and dim.nominal_value != 0):
                    pct = abs(dim.tolerance_value / dim.nominal_value) * 100
                    if pct > 10:
                        issues.append(
                            DetectedIssue(
                                issue_type=IssueType.DIMENSION_OUT_OF_RANGE,
                                severity=SeverityLevel.WARNING,
                                description=(
                                    f"Tolerance {dim.tolerance_value} is {pct:.1f}% "
                                    f"of nominal {dim.nominal_value}. Review if correct."
                                ),
                                affected_items=[dim.id],
                                page_number=page.page_number,
                            )
                        )

        return issues

    # ------------------------------------------------------------------
    # Tolerance rules
    # ------------------------------------------------------------------

    def _check_tolerances(self, pages: list[PageResult]) -> list[DetectedIssue]:
        issues: list[DetectedIssue] = []

        for page in pages:
            for tol in page.tolerances:
                # Fit class validation
                if tol.fit_class:
                    fit = tol.fit_class.strip()
                    is_hole = fit in self.HOLE_BASE_FITS
                    is_shaft = fit in self.SHAFT_BASE_FITS
                    if not is_hole and not is_shaft:
                        issues.append(
                            DetectedIssue(
                                issue_type=IssueType.INCONSISTENT_VALUES,
                                severity=SeverityLevel.WARNING,
                                description=f"Unrecognised fit class: '{fit}'. Verify standard reference.",
                                affected_items=[tol.id],
                                page_number=page.page_number,
                            )
                        )

                # Limit consistency
                if (tol.upper_tolerance is not None and tol.lower_tolerance is not None
                        and tol.nominal_value is not None):
                    ul = tol.nominal_value + tol.upper_tolerance
                    ll = tol.nominal_value + tol.lower_tolerance
                    if tol.upper_limit is not None and abs(ul - tol.upper_limit) > 0.001:
                        issues.append(
                            DetectedIssue(
                                issue_type=IssueType.CALCULATION_MISMATCH,
                                severity=SeverityLevel.WARNING,
                                description=(
                                    f"Computed upper limit ({ul}) differs from stated ({tol.upper_limit})."
                                ),
                                affected_items=[tol.id],
                                page_number=page.page_number,
                            )
                        )
                    if tol.lower_limit is not None and abs(ll - tol.lower_limit) > 0.001:
                        issues.append(
                            DetectedIssue(
                                issue_type=IssueType.CALCULATION_MISMATCH,
                                severity=SeverityLevel.WARNING,
                                description=(
                                    f"Computed lower limit ({ll}) differs from stated ({tol.lower_limit})."
                                ),
                                affected_items=[tol.id],
                                page_number=page.page_number,
                            )
                        )

                # Upper tolerance should be >= lower tolerance
                if (tol.upper_tolerance is not None and tol.lower_tolerance is not None
                        and tol.upper_tolerance < tol.lower_tolerance):
                    issues.append(
                        DetectedIssue(
                            issue_type=IssueType.INCONSISTENT_VALUES,
                            severity=SeverityLevel.ERROR,
                            description=(
                                f"Upper tolerance ({tol.upper_tolerance}) < "
                                f"lower tolerance ({tol.lower_tolerance})."
                            ),
                            affected_items=[tol.id],
                            page_number=page.page_number,
                        )
                    )

        return issues

    # ------------------------------------------------------------------
    # Hole rules
    # ------------------------------------------------------------------

    def _check_holes(self, pages: list[PageResult]) -> list[DetectedIssue]:
        issues: list[DetectedIssue] = []

        for page in pages:
            for hole in page.holes:
                if hole.diameter is not None and hole.diameter <= 0:
                    issues.append(
                        DetectedIssue(
                            issue_type=IssueType.DIMENSION_OUT_OF_RANGE,
                            severity=SeverityLevel.ERROR,
                            description=f"Invalid hole diameter: {hole.diameter}",
                            affected_items=[hole.id],
                            page_number=page.page_number,
                        )
                    )

                if hole.depth is not None and hole.depth <= 0:
                    issues.append(
                        DetectedIssue(
                            issue_type=IssueType.DIMENSION_OUT_OF_RANGE,
                            severity=SeverityLevel.ERROR,
                            description=f"Invalid hole depth: {hole.depth}",
                            affected_items=[hole.id],
                            page_number=page.page_number,
                        )
                    )

                if hole.hole_type == "blind" and hole.depth is None:
                    issues.append(
                        DetectedIssue(
                            issue_type=IssueType.MISSING_TOLERANCE,
                            severity=SeverityLevel.WARNING,
                            description="Blind hole without specified depth.",
                            affected_items=[hole.id],
                            page_number=page.page_number,
                            recommendation="Add depth specification for blind holes.",
                        )
                    )

                if hole.hole_type == "tapped" and not hole.thread_spec:
                    issues.append(
                        DetectedIssue(
                            issue_type=IssueType.MISSING_TOLERANCE,
                            severity=SeverityLevel.WARNING,
                            description="Tapped hole without thread specification.",
                            affected_items=[hole.id],
                            page_number=page.page_number,
                            recommendation="Add thread specification (e.g., M6x1.0).",
                        )
                    )

                if hole.quantity is not None and hole.quantity <= 0:
                    issues.append(
                        DetectedIssue(
                            issue_type=IssueType.DIMENSION_OUT_OF_RANGE,
                            severity=SeverityLevel.ERROR,
                            description=f"Invalid hole quantity: {hole.quantity}",
                            affected_items=[hole.id],
                            page_number=page.page_number,
                        )
                    )

        return issues

    # ------------------------------------------------------------------
    # GD&T rules
    # ------------------------------------------------------------------

    def _check_gd_t(self, pages: list[PageResult]) -> list[DetectedIssue]:
        issues: list[DetectedIssue] = []

        for page in pages:
            for gdt in page.gd_t_items:
                if gdt.characteristic:
                    if gdt.characteristic.lower() not in self.VALID_GD_T_CHARACTERISTICS:
                        issues.append(
                            DetectedIssue(
                                issue_type=IssueType.GD_T_VIOLATION,
                                severity=SeverityLevel.WARNING,
                                description=(
                                    f"Unrecognised GD&T characteristic: '{gdt.characteristic}'. "
                                    f"Verify against ASME Y14.5."
                                ),
                                affected_items=[gdt.id],
                                page_number=page.page_number,
                            )
                        )

                if gdt.tolerance_value is not None and gdt.tolerance_value < 0:
                    issues.append(
                        DetectedIssue(
                            issue_type=IssueType.GD_T_VIOLATION,
                            severity=SeverityLevel.ERROR,
                            description=f"Negative GD&T tolerance value: {gdt.tolerance_value}",
                            affected_items=[gdt.id],
                            page_number=page.page_number,
                        )
                    )

                # Position tolerance should have at least one datum
                if gdt.characteristic and gdt.characteristic.lower() == "position":
                    if not gdt.datum_references:
                        issues.append(
                            DetectedIssue(
                                issue_type=IssueType.MISSING_DATUM,
                                severity=SeverityLevel.WARNING,
                                description="Position tolerance without datum reference.",
                                affected_items=[gdt.id],
                                page_number=page.page_number,
                                recommendation="Position tolerance typically requires datum reference.",
                            )
                        )

        return issues

    # ------------------------------------------------------------------
    # Welding rules
    # ------------------------------------------------------------------

    def _check_welding(self, pages: list[PageResult]) -> list[DetectedIssue]:
        issues: list[DetectedIssue] = []

        for page in pages:
            for weld in page.welding_items:
                if weld.weld_size and weld.weld_type:
                    try:
                        size_val = self._extract_numeric(weld.weld_size)
                        if size_val is not None and size_val <= 0:
                            issues.append(
                                DetectedIssue(
                                    issue_type=IssueType.WELDING_CONFLICT,
                                    severity=SeverityLevel.ERROR,
                                    description=f"Invalid weld size: {weld.weld_size}",
                                    affected_items=[weld.id],
                                    page_number=page.page_number,
                                )
                            )
                    except (ValueError, TypeError):
                        pass

                if not weld.arrow_side and not weld.other_side:
                    issues.append(
                        DetectedIssue(
                            issue_type=IssueType.WELDING_CONFLICT,
                            severity=SeverityLevel.INFO,
                            description="Weld symbol has neither arrow side nor other side indicated.",
                            affected_items=[weld.id],
                            page_number=page.page_number,
                        )
                    )

        return issues

    # ------------------------------------------------------------------
    # Material rules
    # ------------------------------------------------------------------

    def _check_materials(self, pages: list[PageResult]) -> list[DetectedIssue]:
        issues: list[DetectedIssue] = []

        for page in pages:
            for mat in page.materials:
                if mat.material_spec:
                    has_known_std = any(
                        std in mat.material_spec.upper()
                        for std in self.KNOWN_MATERIAL_STANDARDS
                    )
                    if not has_known_std:
                        issues.append(
                            DetectedIssue(
                                issue_type=IssueType.UNVERIFIED,
                                severity=SeverityLevel.INFO,
                                description=(
                                    f"Material spec '{mat.material_spec}' does not contain "
                                    f"a recognised standard prefix."
                                ),
                                affected_items=[mat.id],
                                page_number=page.page_number,
                            )
                        )

        return issues

    # ------------------------------------------------------------------
    # Cross-page consistency
    # ------------------------------------------------------------------

    def _check_cross_page_consistency(self, pages: list[PageResult]) -> list[DetectedIssue]:
        issues: list[DetectedIssue] = []

        # Check for conflicting drawing metadata across pages
        metadata_pages: dict[str, list[int]] = {}
        for page in pages:
            if page.drawing_metadata:
                dm = page.drawing_metadata
                if dm.drawing_number:
                    metadata_pages.setdefault("drawing_number", []).append(page.page_number)
                if dm.revision:
                    metadata_pages.setdefault("revision", []).append(page.page_number)

        # Check BOM part number uniqueness
        seen_parts: dict[str, list[str]] = {}
        for page in pages:
            for bom in page.bom_items:
                if bom.part_number:
                    seen_parts.setdefault(bom.part_number, []).append(
                        f"page {page.page_number}"
                    )

        for pn, locations in seen_parts.items():
            if len(locations) > 1:
                issues.append(
                    DetectedIssue(
                        issue_type=IssueType.INCONSISTENT_VALUES,
                        severity=SeverityLevel.INFO,
                        description=f"Part number '{pn}' appears in multiple locations: {', '.join(locations)}.",
                        page_number=locations[0] if locations else None,
                    )
                )

        return issues

    # ------------------------------------------------------------------
    # Missing information checks
    # ------------------------------------------------------------------

    def _check_missing_information(self, pages: list[PageResult]) -> list[DetectedIssue]:
        issues: list[DetectedIssue] = []
        all_dims = []
        all_tols = []

        for page in pages:
            all_dims.extend(page.dimensions)
            all_tols.extend(page.tolerances)

        # Dimensions without tolerances
        for dim in all_dims:
            if dim.nominal_value is not None and dim.tolerance_value is None and dim.upper_limit is None:
                issues.append(
                    DetectedIssue(
                        issue_type=IssueType.MISSING_TOLERANCE,
                        severity=SeverityLevel.INFO,
                        description=f"Dimension '{dim.value}' has no tolerance specified.",
                        affected_items=[dim.id],
                        page_number=dim.page_number,
                        recommendation="Verify if tolerance block or general tolerance applies.",
                    )
                )

        # Pages without material info
        pages_with_material = {p.page_number for p in pages for m in p.materials}
        for page in pages:
            if (page.page_number not in pages_with_material
                    and (page.dimensions or page.holes)):
                # Only warn if the page has engineering content
                if any(v for v in page.other_annotations if "material" in str(v.value).lower()):
                    continue  # Material mentioned in annotations
                issues.append(
                    DetectedIssue(
                        issue_type=IssueType.MISSING_MATERIAL,
                        severity=SeverityLevel.INFO,
                        description=f"Page {page.page_number} has dimensions/holes but no material specified.",
                        page_number=page.page_number,
                    )
                )

        return issues

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_numeric(text: str) -> Optional[float]:
        """Extract first numeric value from text."""
        match = re.search(r"[-+]?\d*\.?\d+", text)
        if match:
            return float(match.group())
        return None

    @staticmethod
    def calculate_upper_lower(
        nominal: float,
        upper_tol: Optional[float] = None,
        lower_tol: Optional[float] = None,
        symmetric_tol: Optional[float] = None,
    ) -> tuple[float, float]:
        """Calculate upper and lower limits from tolerance specification."""
        if symmetric_tol is not None:
            return nominal + symmetric_tol, nominal - symmetric_tol
        upper = nominal + (upper_tol if upper_tol is not None else 0)
        lower = nominal + (lower_tol if lower_tol is not None else 0)
        return upper, lower

    # ------------------------------------------------------------------
    # Criticality Classification
    # ------------------------------------------------------------------

    def _classify_all(self, page_results: list[PageResult]) -> None:
        """Classify criticality and assign control/inspection modes for all items."""
        # Collect all critical characteristics to cross-reference
        critical_features = self._collect_critical_features(page_results)

        for pr in page_results:
            for dim in pr.dimensions:
                dim.criticality = self._classify_dimension_criticality(dim, critical_features)
                dim.mode_of_control = self._assign_mode_of_control(dim)
                dim.mode_of_inspection = self._assign_mode_of_inspection(dim)
                dim.specification = self._build_specification(dim)

            for tol in pr.tolerances:
                tol.criticality = self._classify_tolerance_criticality(tol, critical_features)
                tol.mode_of_control = self._assign_tol_control(tol)
                tol.mode_of_inspection = self._assign_tol_inspection(tol)
                tol.specification = self._build_tol_specification(tol)

            for hole in pr.holes:
                hole.criticality = self._classify_hole_criticality(hole, critical_features)
                hole.mode_of_control = self._assign_hole_control(hole)
                hole.mode_of_inspection = self._assign_hole_inspection(hole)
                hole.specification = self._build_hole_specification(hole)

    @staticmethod
    def _collect_critical_features(page_results: list[PageResult]) -> set[str]:
        """Collect all explicitly marked critical feature references."""
        features: set[str] = set()
        for pr in page_results:
            for cc in pr.critical_characteristics:
                if cc.feature_ref:
                    features.add(cc.feature_ref.lower())
                if cc.value:
                    features.add(str(cc.value).lower())
            # GD&T with tight tolerances implies criticality
            for gdt in pr.gd_t_items:
                if gdt.tolerance_value is not None and gdt.tolerance_value <= 0.05:
                    if gdt.feature_control_frame:
                        features.add(gdt.feature_control_frame.lower())
        return features

    def _classify_dimension_criticality(
        self, dim: DimensionItem, critical_features: set[str]
    ) -> CriticalityLevel:
        """Determine if a dimension is critical based on deterministic rules."""
        # Rule 1: Tight tolerance implies critical
        if dim.tolerance_value is not None and dim.tolerance_value > 0:
            if dim.nominal_value is not None and dim.nominal_value != 0:
                pct = abs(dim.tolerance_value / dim.nominal_value) * 100
                if pct <= 1.0:
                    return CriticalityLevel.CRITICAL
                if pct <= 2.0:
                    return CriticalityLevel.CRITICAL

        # Rule 2: Small absolute tolerance (< 0.1mm) is critical
        if dim.tolerance_value is not None and abs(dim.tolerance_value) <= 0.1:
            return CriticalityLevel.CRITICAL

        # Rule 3: Diameter dimensions with tight tolerance
        if dim.dimension_type == "diameter" and dim.tolerance_value is not None:
            if abs(dim.tolerance_value) <= 0.05:
                return CriticalityLevel.CRITICAL

        # Rule 4: Referenced by critical characteristic
        if dim.source_text and dim.source_text.lower() in critical_features:
            return CriticalityLevel.CRITICAL

        # Rule 5: GD&T controlled dimensions are critical
        if dim.leader_text and any(
            sym in (dim.leader_text or "").upper()
            for sym in ["⌖", "⊥", "∥", "○", "⌓", "↗"]
        ):
            return CriticalityLevel.CRITICAL

        return CriticalityLevel.NON_CRITICAL

    def _classify_tolerance_criticality(
        self, tol: ToleranceItem, critical_features: set[str]
    ) -> CriticalityLevel:
        """Determine if a tolerance is critical."""
        if tol.upper_tolerance is not None and tol.lower_tolerance is not None:
            avg = (abs(tol.upper_tolerance) + abs(tol.lower_tolerance)) / 2
            if avg <= 0.05:
                return CriticalityLevel.CRITICAL
            if avg <= 0.1:
                return CriticalityLevel.CRITICAL

        if tol.fit_class:
            # H7, g6 and tighter are critical fits
            fit = tol.fit_class.strip()
            if len(fit) >= 2 and fit[1:].isdigit():
                try:
                    it_grade = int(fit[1:])
                    if it_grade <= 6:
                        return CriticalityLevel.CRITICAL
                except ValueError:
                    pass

        return CriticalityLevel.NON_CRITICAL

    def _classify_hole_criticality(
        self, hole: HoleItem, critical_features: set[str]
    ) -> CriticalityLevel:
        """Determine if a hole is critical."""
        if hole.hole_type == "tapped":
            return CriticalityLevel.CRITICAL
        if hole.diameter is not None and hole.diameter <= 3.0:
            return CriticalityLevel.CRITICAL
        if hole.thread_spec:
            return CriticalityLevel.CRITICAL
        return CriticalityLevel.NON_CRITICAL

    # ------------------------------------------------------------------
    # Mode of Control assignment
    # ------------------------------------------------------------------

    @staticmethod
    def _assign_mode_of_control(dim: DimensionItem) -> ModeOfControl:
        """Assign mode of control based on dimension characteristics."""
        if dim.tolerance_value is not None and abs(dim.tolerance_value) <= 0.01:
            return ModeOfControl.CNC
        if dim.tolerance_value is not None and abs(dim.tolerance_value) <= 0.05:
            return ModeOfControl.CNC
        if dim.dimension_type == "angular":
            return ModeOfControl.MANUAL
        if dim.tolerance_value is not None and abs(dim.tolerance_value) <= 0.5:
            return ModeOfControl.CNC
        return ModeOfControl.MANUAL

    @staticmethod
    def _assign_tol_control(tol: ToleranceItem) -> ModeOfControl:
        if tol.fit_class:
            fit = tol.fit_class.strip()
            if len(fit) >= 2 and fit[1:].isdigit():
                try:
                    it_grade = int(fit[1:])
                    if it_grade <= 7:
                        return ModeOfControl.CNC
                except ValueError:
                    pass
        if tol.upper_tolerance is not None and abs(tol.upper_tolerance) <= 0.05:
            return ModeOfControl.CMM
        return ModeOfControl.MANUAL

    @staticmethod
    def _assign_hole_control(hole: HoleItem) -> ModeOfControl:
        if hole.hole_type == "tapped":
            return ModeOfControl.CNC
        if hole.diameter is not None and hole.diameter <= 5.0:
            return ModeOfControl.CNC
        return ModeOfControl.MANUAL

    # ------------------------------------------------------------------
    # Mode of Inspection assignment
    # ------------------------------------------------------------------

    @staticmethod
    def _assign_mode_of_inspection(dim: DimensionItem) -> ModeOfInspection:
        if dim.tolerance_value is not None and abs(dim.tolerance_value) <= 0.01:
            return ModeOfInspection.CMM
        if dim.tolerance_value is not None and abs(dim.tolerance_value) <= 0.05:
            return ModeOfInspection.CMM
        if dim.tolerance_value is not None and abs(dim.tolerance_value) <= 0.5:
            return ModeOfInspection.GO_NOGO
        return ModeOfInspection.VISUAL

    @staticmethod
    def _assign_tol_inspection(tol: ToleranceItem) -> ModeOfInspection:
        if tol.fit_class:
            return ModeOfInspection.CMM
        if tol.upper_tolerance is not None and abs(tol.upper_tolerance) <= 0.05:
            return ModeOfInspection.CMM
        return ModeOfInspection.GO_NOGO

    @staticmethod
    def _assign_hole_inspection(hole: HoleItem) -> ModeOfInspection:
        if hole.hole_type == "tapped":
            return ModeOfInspection.GO_NOGO
        if hole.diameter is not None and hole.diameter <= 5.0:
            return ModeOfInspection.CMM
        return ModeOfInspection.GO_NOGO

    # ------------------------------------------------------------------
    # Specification builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_specification(dim: DimensionItem) -> str:
        parts: list[str] = []
        if dim.nominal_value is not None:
            parts.append(str(dim.nominal_value))
        elif dim.value:
            parts.append(str(dim.value))

        if dim.tolerance_value is not None:
            parts.append(f"+/- {dim.tolerance_value}")
        elif dim.upper_limit is not None and dim.lower_limit is not None:
            parts.append(f"({dim.lower_limit} to {dim.upper_limit})")

        if dim.unit:
            parts.append(dim.unit)

        return " ".join(parts) if parts else str(dim.value)

    @staticmethod
    def _build_tol_specification(tol: ToleranceItem) -> str:
        parts: list[str] = []
        if tol.nominal_value is not None:
            parts.append(str(tol.nominal_value))
        elif tol.value:
            parts.append(str(tol.value))

        if tol.upper_tolerance is not None and tol.lower_tolerance is not None:
            parts.append(f"+{tol.upper_tolerance}/{tol.lower_tolerance}")
        elif tol.fit_class:
            parts.append(f"[{tol.fit_class}]")
        elif tol.upper_limit is not None and tol.lower_limit is not None:
            parts.append(f"({tol.lower_limit} to {tol.upper_limit})")

        if tol.unit:
            parts.append(tol.unit)

        return " ".join(parts) if parts else str(tol.value)

    @staticmethod
    def _build_hole_specification(hole: HoleItem) -> str:
        parts: list[str] = []
        if hole.diameter is not None:
            parts.append(f"Ø{hole.diameter}")
        elif hole.value:
            parts.append(str(hole.value))

        if hole.depth is not None:
            parts.append(f"x {hole.depth} deep")
        if hole.thread_spec:
            parts.append(f"({hole.thread_spec})")
        if hole.quantity and hole.quantity > 1:
            parts.append(f"x{hole.quantity} places")

        return " ".join(parts) if parts else str(hole.value)
