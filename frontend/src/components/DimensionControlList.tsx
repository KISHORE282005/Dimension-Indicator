import type { DimensionControlRow, DimensionItem, HoleItem, ToleranceItem } from "../types";

interface Props {
  rows: DimensionControlRow[];
  allDimensions: DimensionItem[];
  allHoles: HoleItem[];
  allTolerances: ToleranceItem[];
}

export default function DimensionControlList({ rows, allDimensions, allHoles, allTolerances }: Props) {
  const displayRows = rows.length > 0 ? rows : buildFromRaw(allDimensions, allHoles, allTolerances);
  const criticalCount = displayRows.filter((r) => r.criticality === "Critical").length;
  const nonCriticalCount = displayRows.length - criticalCount;

  return (
    <div className="dcl-container">
      <div className="dcl-header">
        <h2>Dimension Control List</h2>
        <div className="dcl-stats">
          <span className="dcl-stat">Total: <strong>{displayRows.length}</strong></span>
          <span className="dcl-stat critical-stat">Critical: <strong>{criticalCount}</strong></span>
          <span className="dcl-stat non-critical-stat">Non-Critical: <strong>{nonCriticalCount}</strong></span>
        </div>
      </div>
      <div className="table-scroll">
        <table className="data-table dcl-table">
          <thead>
            <tr>
              <th>Dimension No.</th>
              <th>Specification</th>
              <th>Criticality</th>
              <th>Mode of Control</th>
              <th>Mode of Inspection</th>
              <th>Page</th>
            </tr>
          </thead>
          <tbody>
            {displayRows.map((row) => (
              <tr key={`${row.dimension_number}-${row.original_id}`} className={row.criticality === "Critical" ? "row-critical" : ""}>
                <td className="mono dim-num">{row.dimension_number}</td>
                <td className="mono spec-cell">{row.specification}</td>
                <td><span className={`criticality-badge ${row.criticality === "Critical" ? "critical" : "non-critical"}`}>{row.criticality}</span></td>
                <td>{row.mode_of_control}</td>
                <td>{row.mode_of_inspection}</td>
                <td>{row.page_number || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {displayRows.length === 0 && <p className="no-data">No dimensional features extracted.</p>}
    </div>
  );
}

function buildFromRaw(dims: DimensionItem[], holes: HoleItem[], tols: ToleranceItem[]): DimensionControlRow[] {
  const rows: DimensionControlRow[] = [];
  let seq = 1;
  for (const d of dims) {
    const spec = d.specification || String(d.value);
    rows.push({ dimension_number: seq++, specification: spec, criticality: d.criticality || "Non-Critical", mode_of_control: d.mode_of_control || "Not Defined", mode_of_inspection: d.mode_of_inspection || "Not Defined", nominal_value: d.nominal_value, upper_limit: d.upper_limit, lower_limit: d.lower_limit, tolerance_value: d.tolerance_value, unit: d.unit, page_number: d.page_number, source_type: typeof d.source_type === "string" ? d.source_type : "deterministic", confidence: d.confidence, category: "Dimension", original_id: d.id });
  }
  for (const t of tols) {
    const spec = t.specification || String(t.value);
    rows.push({ dimension_number: seq++, specification: spec, criticality: t.criticality || "Non-Critical", mode_of_control: t.mode_of_control || "Not Defined", mode_of_inspection: t.mode_of_inspection || "Not Defined", nominal_value: t.nominal_value, upper_limit: t.upper_limit, lower_limit: t.lower_limit, tolerance_value: t.upper_tolerance, unit: t.unit, page_number: t.page_number, source_type: typeof t.source_type === "string" ? t.source_type : "deterministic", confidence: t.confidence, category: "Tolerance", original_id: t.id });
  }
  for (const h of holes) {
    const spec = h.specification || String(h.value);
    rows.push({ dimension_number: seq++, specification: spec, criticality: h.criticality || "Non-Critical", mode_of_control: h.mode_of_control || "Not Defined", mode_of_inspection: h.mode_of_inspection || "Not Defined", nominal_value: h.diameter, upper_limit: null, lower_limit: null, tolerance_value: null, unit: "mm", page_number: h.page_number, source_type: typeof h.source_type === "string" ? h.source_type : "deterministic", confidence: h.confidence, category: "Hole", original_id: h.id });
  }
  return rows;
}
