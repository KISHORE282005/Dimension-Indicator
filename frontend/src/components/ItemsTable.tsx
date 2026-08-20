import type { HoleItem, WeldingItem, GDTItem, SurfaceFinishItem, BOMItem, ManufacturingNote, DatumItem, MaterialItem } from "../types";

interface ItemsSectionProps<T> {
  title: string;
  icon: string;
  items: T[];
  renderRow: (item: T, index: number) => React.ReactNode;
  columns: string[];
}

function ItemsSection<T>({ title, icon, items, renderRow, columns }: ItemsSectionProps<T>) {
  if (items.length === 0) return null;
  return (
    <div className="data-table-container">
      <h3>
        {icon} {title} ({items.length})
      </h3>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>{items.map((item, idx) => renderRow(item, idx))}</tbody>
        </table>
      </div>
    </div>
  );
}

export function HoleTable({ items }: { items: HoleItem[] }) {
  return (
    <ItemsSection
      title="Holes"
      icon="🔩"
      items={items}
      columns={["No.", "Type", "Diameter", "Depth", "Thread", "Qty", "Specification", "Criticality", "Control", "Inspection", "Confidence"]}
      renderRow={(h, idx) => (
        <tr key={h.id} className={h.criticality === "Critical" ? "row-critical" : ""}>
          <td>{h.dimension_number || idx + 1}</td>
          <td>{h.hole_type || "-"}</td>
          <td className="mono">{h.diameter ?? "-"}</td>
          <td className="mono">{h.depth ?? "-"}</td>
          <td>{h.thread_spec || "-"}</td>
          <td>{h.quantity ?? "-"}</td>
          <td className="mono">{h.specification || "-"}</td>
          <td><span className={`criticality-badge ${h.criticality === "Critical" ? "critical" : "non-critical"}`}>{h.criticality || "Non-Critical"}</span></td>
          <td>{h.mode_of_control || "Not Defined"}</td>
          <td>{h.mode_of_inspection || "Not Defined"}</td>
          <td><span className={`confidence ${h.confidence >= 0.8 ? "high" : h.confidence >= 0.5 ? "medium" : "low"}`}>{(h.confidence * 100).toFixed(0)}%</span></td>
        </tr>
      )}
    />
  );
}

export function WeldingTable({ items }: { items: WeldingItem[] }) {
  return (
    <ItemsSection
      title="Welding"
      icon="🔥"
      items={items}
      columns={["Page", "Type", "Size", "Length", "Joint", "Arrow", "Other", "Confidence"]}
      renderRow={(w) => (
        <tr key={w.id}>
          <td>{w.page_number}</td>
          <td>{w.weld_type || "-"}</td>
          <td>{w.weld_size || "-"}</td>
          <td>{w.weld_length || "-"}</td>
          <td>{w.joint_type || "-"}</td>
          <td>{w.arrow_side ? "✓" : "-"}</td>
          <td>{w.other_side ? "✓" : "-"}</td>
          <td><span className={`confidence ${w.confidence >= 0.8 ? "high" : w.confidence >= 0.5 ? "medium" : "low"}`}>{(w.confidence * 100).toFixed(0)}%</span></td>
        </tr>
      )}
    />
  );
}

export function GDTTable({ items }: { items: GDTItem[] }) {
  return (
    <ItemsSection
      title="GD&T"
      icon="📐"
      items={items}
      columns={["Page", "Characteristic", "Value", "Datums", "Modifier", "Confidence"]}
      renderRow={(g) => (
        <tr key={g.id}>
          <td>{g.page_number}</td>
          <td>{g.characteristic || "-"}</td>
          <td className="mono">{g.tolerance_value ?? "-"}</td>
          <td>{g.datum_references?.join(", ") || "-"}</td>
          <td>{g.modifier || "-"}</td>
          <td><span className={`confidence ${g.confidence >= 0.8 ? "high" : g.confidence >= 0.5 ? "medium" : "low"}`}>{(g.confidence * 100).toFixed(0)}%</span></td>
        </tr>
      )}
    />
  );
}

export function SurfaceFinishTable({ items }: { items: SurfaceFinishItem[] }) {
  return (
    <ItemsSection
      title="Surface Finish"
      icon="✨"
      items={items}
      columns={["Page", "Roughness", "Unit", "Method", "Confidence"]}
      renderRow={(s) => (
        <tr key={s.id}>
          <td>{s.page_number}</td>
          <td className="mono">{s.roughness_value ?? "-"}</td>
          <td>{s.roughness_unit || "-"}</td>
          <td>{s.surface_method || "-"}</td>
          <td><span className={`confidence ${s.confidence >= 0.8 ? "high" : s.confidence >= 0.5 ? "medium" : "low"}`}>{(s.confidence * 100).toFixed(0)}%</span></td>
        </tr>
      )}
    />
  );
}

export function BOMTable({ items }: { items: BOMItem[] }) {
  return (
    <ItemsSection
      title="BOM / Parts"
      icon="📦"
      items={items}
      columns={["Page", "Part No.", "Description", "Qty", "Material", "Confidence"]}
      renderRow={(b) => (
        <tr key={b.id}>
          <td>{b.page_number}</td>
          <td>{b.part_number || "-"}</td>
          <td>{b.description || "-"}</td>
          <td>{b.quantity ?? "-"}</td>
          <td>{b.material || "-"}</td>
          <td><span className={`confidence ${b.confidence >= 0.8 ? "high" : b.confidence >= 0.5 ? "medium" : "low"}`}>{(b.confidence * 100).toFixed(0)}%</span></td>
        </tr>
      )}
    />
  );
}

export function NotesList({ items }: { items: ManufacturingNote[] }) {
  if (items.length === 0) return null;
  return (
    <div className="data-table-container">
      <h3>📝 Manufacturing Notes ({items.length})</h3>
      <div className="notes-list">
        {items.map((n) => (
          <div key={n.id} className="note-item">
            <span className="note-number">{n.note_number || "-"}</span>
            <span className="note-text">{n.note_text || String(n.value)}</span>
            <span className="note-page">Page {n.page_number}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function DatumsTable({ items }: { items: DatumItem[] }) {
  return (
    <ItemsSection
      title="Datums"
      icon="📍"
      items={items}
      columns={["Page", "Label", "Type", "Feature", "Confidence"]}
      renderRow={(d) => (
        <tr key={d.id}>
          <td>{d.page_number}</td>
          <td className="mono">{d.datum_label || "-"}</td>
          <td>{d.datum_type || "-"}</td>
          <td>{d.feature_description || "-"}</td>
          <td><span className={`confidence ${d.confidence >= 0.8 ? "high" : d.confidence >= 0.5 ? "medium" : "low"}`}>{(d.confidence * 100).toFixed(0)}%</span></td>
        </tr>
      )}
    />
  );
}

export function MaterialsTable({ items }: { items: MaterialItem[] }) {
  return (
    <ItemsSection
      title="Materials"
      icon="🧱"
      items={items}
      columns={["Page", "Spec", "Name", "Grade", "Confidence"]}
      renderRow={(m) => (
        <tr key={m.id}>
          <td>{m.page_number}</td>
          <td>{m.material_spec || "-"}</td>
          <td>{m.material_name || "-"}</td>
          <td>{m.material_grade || "-"}</td>
          <td><span className={`confidence ${m.confidence >= 0.8 ? "high" : m.confidence >= 0.5 ? "medium" : "low"}`}>{(m.confidence * 100).toFixed(0)}%</span></td>
        </tr>
      )}
    />
  );
}
