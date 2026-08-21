export interface DrawingMetadata {
  drawing_number: string | null;
  revision: string | null;
  title: string | null;
  scale: string | null;
  drawn_by: string | null;
  checked_by: string | null;
  approved_by: string | null;
  date: string | null;
  company: string | null;
  drawing_standard: string | null;
}

export interface ExtractedItem {
  id: string;
  value: any;
  category: string;
  page_number: number;
  confidence: number;
  bounding_box: number[] | null;
  source_text: string | null;
  source_type: string;
  extracted_at: string;
}

export interface DimensionItem extends ExtractedItem {
  dimension_number: number | null;
  dimension_type: string | null;
  nominal_value: number | null;
  unit: string | null;
  upper_limit: number | null;
  lower_limit: number | null;
  tolerance_value: number | null;
  specification: string | null;
  is_baseline: boolean;
  reference_only: boolean;
  criticality: string;
  mode_of_control: string;
  mode_of_inspection: string;
}

export interface ToleranceItem extends ExtractedItem {
  dimension_number: number | null;
  nominal_value: number | null;
  upper_tolerance: number | null;
  lower_tolerance: number | null;
  upper_limit: number | null;
  lower_limit: number | null;
  fit_class: string | null;
  tolerance_zone: string | null;
  specification: string | null;
  criticality: string;
  mode_of_control: string;
  mode_of_inspection: string;
  unit: string | null;
}

export interface HoleItem extends ExtractedItem {
  dimension_number: number | null;
  hole_type: string | null;
  diameter: number | null;
  depth: number | null;
  thread_spec: string | null;
  quantity: number | null;
  specification: string | null;
  criticality: string;
  mode_of_control: string;
  mode_of_inspection: string;
}

export interface WeldingItem extends ExtractedItem {
  weld_type: string | null;
  weld_size: string | null;
  weld_length: string | null;
  joint_type: string | null;
  arrow_side: boolean;
  other_side: boolean;
}

export interface GDTItem extends ExtractedItem {
  characteristic: string | null;
  symbol: string | null;
  tolerance_value: number | null;
  tolerance_zone_shape: string | null;
  modifier: string | null;
  datum_references: string[];
  primary_datum: string | null;
  feature_control_frame: string | null;
}

export interface DatumItem extends ExtractedItem {
  datum_label: string | null;
  datum_type: string | null;
  feature_description: string | null;
}

export interface SurfaceFinishItem extends ExtractedItem {
  roughness_value: number | null;
  roughness_unit: string | null;
  surface_method: string | null;
}

export interface MaterialItem extends ExtractedItem {
  material_spec: string | null;
  material_name: string | null;
  material_grade: string | null;
}

export interface ManufacturingNote extends ExtractedItem {
  note_number: number | null;
  note_text: string;
  note_type: string | null;
}

export interface BOMItem extends ExtractedItem {
  part_number: string | null;
  description: string | null;
  quantity: number | null;
  material: string | null;
}

export interface SectionView extends ExtractedItem {
  section_label: string | null;
  view_direction: string | null;
}

export interface DetailView extends ExtractedItem {
  detail_label: string | null;
  scale: string | null;
}

export interface DetectedIssue {
  id: string;
  issue_type: string;
  severity: string;
  description: string;
  affected_items: string[];
  page_number: number | null;
  recommendation: string | null;
  extracted_at: string;
}

export interface ValidationResult {
  is_valid: boolean;
  issues: DetectedIssue[];
  warnings: DetectedIssue[];
  rules_applied: string[];
}

export interface AIInterpretation {
  id: string;
  source_type: string;
  page_number: number;
  interpretation_text: string;
  extracted_items: ExtractedItem[];
  confidence: number;
  model_used: string;
  disclaimer: string;
}

export interface PageResult {
  page_number: number;
  page_width: number;
  page_height: number;
  drawing_metadata: DrawingMetadata | null;
  bom_items: BOMItem[];
  dimensions: DimensionItem[];
  tolerances: ToleranceItem[];
  holes: HoleItem[];
  welding_items: WeldingItem[];
  gd_t_items: GDTItem[];
  datums: DatumItem[];
  surface_finishes: SurfaceFinishItem[];
  materials: MaterialItem[];
  manufacturing_notes: ManufacturingNote[];
  section_views: SectionView[];
  detail_views: DetailView[];
  critical_characteristics: ExtractedItem[];
  other_annotations: ExtractedItem[];
  ai_interpretations: AIInterpretation[];
  processing_time_seconds: number;
}

export interface DocumentAnalysisResult {
  document_id: string;
  filename: string;
  file_path: string;
  total_pages: number;
  processing_started: string;
  processing_completed: string | null;
  total_processing_time_seconds: number;
  page_results: PageResult[];
  validation_result: ValidationResult | null;
  all_issues: DetectedIssue[];
  extraction_summary: Record<string, number>;
  consolidated_dimension_control: DimensionControlRow[];
}

export interface DimensionControlRow {
  dimension_number: number;
  specification: string;
  criticality: string;
  mode_of_control: string;
  mode_of_inspection: string;
  nominal_value: number | null;
  upper_limit: number | null;
  lower_limit: number | null;
  tolerance_value: number | null;
  unit: string | null;
  page_number: number | null;
  source_type: string;
  confidence: number;
  category: string;
  original_id: string;
}

export interface UploadResponse {
  document_id: string;
  filename: string;
  file_path: string;
  file_size: number;
}

export interface AnalyzeResponse {
  document_id: string;
  filename: string;
  total_pages: number;
  processing_time: number;
  summary: Record<string, number>;
  is_valid: boolean | null;
  issues_count: number;
}

export interface HistoryItem {
  document_id: string;
  filename: string;
  total_pages: number;
  processing_completed: string | null;
  extraction_summary: string;
  is_valid: number;
  issues_count: number;
  warnings_count: number;
  created_at: string;
}
