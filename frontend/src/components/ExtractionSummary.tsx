// Extraction summary component

interface Props {
  summary: Record<string, number>;
  totalPages: number;
  isValid: boolean | null;
  processingTime: number;
}

const CATEGORY_LABELS: Record<string, string> = {
  dimensions: "Dimensions",
  tolerances: "Tolerances",
  holes: "Holes",
  welding_items: "Welding Items",
  gd_t_items: "GD&T Items",
  datums: "Datums",
  surface_finishes: "Surface Finishes",
  materials: "Materials",
  manufacturing_notes: "Mfg Notes",
  bom_items: "BOM Items",
  section_views: "Section Views",
  detail_views: "Detail Views",
  critical_characteristics: "Critical Chars",
};

const CATEGORY_ICONS: Record<string, string> = {
  dimensions: "📏",
  tolerances: "⚙️",
  holes: "🔩",
  welding_items: "🔥",
  gd_t_items: "📐",
  datums: "📍",
  surface_finishes: "✨",
  materials: "🧱",
  manufacturing_notes: "📝",
  bom_items: "📦",
  section_views: "🔪",
  detail_views: "🔍",
  critical_characteristics: "⚠️",
};

export default function ExtractionSummary({
  summary,
  totalPages,
  isValid,
  processingTime,
}: Props) {
  return (
    <div className="summary-panel">
      <h3>Extraction Summary</h3>

      <div className="summary-stats">
        <div className="stat">
          <span className="stat-value">{totalPages}</span>
          <span className="stat-label">Pages</span>
        </div>
        <div className="stat">
          <span className="stat-value">{processingTime.toFixed(1)}s</span>
          <span className="stat-label">Time</span>
        </div>
        <div className="stat">
          <span className={`stat-value ${isValid ? "valid" : "invalid"}`}>
            {isValid === null ? "N/A" : isValid ? "PASS" : "FAIL"}
          </span>
          <span className="stat-label">Status</span>
        </div>
      </div>

      <div className="summary-grid">
        {Object.entries(summary)
          .filter(([_, count]) => count > 0)
          .sort((a, b) => b[1] - a[1])
          .map(([key, count]) => (
            <div key={key} className="summary-item">
              <span className="summary-icon">
                {CATEGORY_ICONS[key] || "📊"}
              </span>
              <span className="summary-count">{count}</span>
              <span className="summary-label">
                {CATEGORY_LABELS[key] || key}
              </span>
            </div>
          ))}
      </div>
    </div>
  );
}
