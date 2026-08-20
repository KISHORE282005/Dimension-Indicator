import type { DimensionItem } from "../types";

interface Props {
  items: DimensionItem[];
}

export default function DimensionTable({ items }: Props) {
  if (items.length === 0)
    return <p className="no-data">No dimensions extracted.</p>;

  const criticalCount = items.filter((d) => d.criticality === "Critical").length;

  return (
    <div className="data-table-container">
      <h3>
        Dimensions ({items.length})
        {criticalCount > 0 && (
          <span className="critical-count"> — {criticalCount} Critical</span>
        )}
      </h3>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Dim No.</th>
              <th>Specification</th>
              <th>Criticality</th>
              <th>Mode of Control</th>
              <th>Mode of Inspection</th>
              <th>Nominal</th>
              <th>Upper</th>
              <th>Lower</th>
              <th>Tolerance</th>
              <th>Unit</th>
              <th>Confidence</th>
              <th>Source</th>
              <th>Page</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, idx) => (
              <tr key={item.id} className={item.criticality === "Critical" ? "row-critical" : ""}>
                <td className="mono">{item.dimension_number || idx + 1}</td>
                <td className="mono">{item.specification || String(item.value)}</td>
                <td>
                  <span className={`criticality-badge ${item.criticality === "Critical" ? "critical" : "non-critical"}`}>
                    {item.criticality || "Non-Critical"}
                  </span>
                </td>
                <td>{item.mode_of_control || "Not Defined"}</td>
                <td>{item.mode_of_inspection || "Not Defined"}</td>
                <td className="mono">
                  {item.nominal_value !== null ? item.nominal_value : "-"}
                </td>
                <td className="mono">
                  {item.upper_limit !== null ? item.upper_limit : "-"}
                </td>
                <td className="mono">
                  {item.lower_limit !== null ? item.lower_limit : "-"}
                </td>
                <td className="mono">
                  {item.tolerance_value !== null ? item.tolerance_value : "-"}
                </td>
                <td>{item.unit || "-"}</td>
                <td>
                  <span
                    className={`confidence ${getConfidenceClass(item.confidence)}`}
                  >
                    {(item.confidence * 100).toFixed(0)}%
                  </span>
                </td>
                <td>
                  <span className={`source-badge ${item.source_type}`}>
                    {item.source_type}
                  </span>
                </td>
                <td>{item.page_number}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function getConfidenceClass(conf: number): string {
  if (conf >= 0.8) return "high";
  if (conf >= 0.5) return "medium";
  return "low";
}
