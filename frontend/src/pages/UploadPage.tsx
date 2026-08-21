import { useCallback, useEffect, useMemo, useState } from "react";
import { useDropzone } from "react-dropzone";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  Play,
  RotateCcw,
  UploadCloud,
} from "lucide-react";
import { useWorkspace } from "../context/WorkspaceContext";
import { getPartExcelUrl } from "../services/api";
import type { CellStatus, DrawingFinding } from "../types";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function cellClass(status: CellStatus): string {
  switch (status) {
    case "filled":
      return "cell-filled";
    case "conflict":
      return "cell-conflict";
    case "missing":
      return "cell-missing";
    default:
      return "";
  }
}

export default function UploadPage() {
  const {
    phase,
    fileName,
    fileSize,
    pageCount,
    documentId,
    jobId,
    progress,
    stage,
    detail,
    error,
    result,
    handleFiles,
    runAnalysis,
    reset,
  } = useWorkspace();
  const [useVlm, setUseVlm] = useState(true);
  const [elapsed, setElapsed] = useState(0);
  const [categoryFilter, setCategoryFilter] = useState<string>("all");

  useEffect(() => {
    if (phase !== "analyzing") {
      setElapsed(0);
      return;
    }
    const t = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, [phase]);

  const onDrop = useCallback(
    (files: File[]) => handleFiles(files),
    [handleFiles]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "image/*": [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"],
    },
    maxFiles: 1,
    multiple: false,
    disabled: phase === "uploading" || phase === "analyzing",
  });

  const categories = useMemo(() => {
    if (!result) return [];
    return Array.from(new Set(result.findings.map((f) => f.category))).sort();
  }, [result]);

  const filteredFindings: DrawingFinding[] = useMemo(() => {
    if (!result) return [];
    if (categoryFilter === "all") return result.findings;
    return result.findings.filter((f) => f.category === categoryFilter);
  }, [result, categoryFilter]);

  return (
    <div className="page upload-page">
      <header className="page-header">
        <h1>Engineering Drawing Analysis</h1>
        <p>
          Upload an engineering diagram to automatically extract dimensions,
          tolerances, GD&amp;T callouts and part data — then generate your
          report in the fixed Excel format: S No, PART NO, DESCRIPTION, DWG NO,
          WEIGHT (IN KG), THICKNESS, PROCESS, LENGTH, WIDTH and HEIGHT.
        </p>
      </header>

      {(phase === "idle" || phase === "uploading") && (
        <div
          {...getRootProps()}
          className={`dropzone-main ${isDragActive ? "active" : ""} ${
            phase === "uploading" ? "disabled" : ""
          }`}
        >
          <input {...getInputProps()} />
          {phase === "uploading" ? (
            <>
              <Loader2 size={34} className="spin accent" />
              <div className="dz-primary">{stage || "Uploading..."}</div>
            </>
          ) : (
            <>
              <UploadCloud size={34} strokeWidth={1.5} />
              <div className="dz-primary">
                {isDragActive
                  ? "Drop the file here..."
                  : "Drag & drop your drawing here, or click to browse"}
              </div>
              <div className="dz-secondary">
                Supports PDF, JPG, PNG, TIFF, BMP, WebP — every page is
                analysed
              </div>
            </>
          )}
        </div>
      )}

      {phase === "ready" && (
        <div className="workspace-card">
          <div className="file-ready-row">
            <FileText size={26} className="file-icon" />
            <div className="file-info">
              <strong>{fileName}</strong>
              <span>
                {formatSize(fileSize)} &middot; {pageCount} page
                {pageCount === 1 ? "" : "s"} &middot; ready to analyze
              </span>
            </div>
            <button className="btn btn-secondary" onClick={reset}>
              <RotateCcw size={14} /> Remove
            </button>
          </div>

          <label className="checkbox-label analyze-toggle">
            <input
              type="checkbox"
              checked={useVlm}
              onChange={(e) => setUseVlm(e.target.checked)}
            />
            <span>Enable AI Vision Analysis (Gemini)</span>
          </label>

          <div className="analyze-actions">
            <button
              className="btn btn-primary btn-lg"
              onClick={() => runAnalysis(useVlm)}
            >
              <Play size={16} /> Run Analysis
            </button>
            <span className="action-hint">
              The report is generated in the fixed 10-column format after
              analysis.
            </span>
          </div>
        </div>
      )}

      {phase === "analyzing" && (
        <div className="workspace-card">
          <div className="file-ready-row">
            <Loader2 size={24} className="spin accent" />
            <div className="file-info">
              <strong>Analyzing {fileName}</strong>
              <span>
                {stage || "Processing"}
                {detail ? ` — ${detail}` : ""} &middot; {elapsed}s elapsed
              </span>
            </div>
            <span className="progress-pct">{progress}%</span>
          </div>
          <div className="progress-bar analyzing">
            <div className="progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <p className="action-hint">
            Large multi-page drawings can take a few minutes. Keep this page
            open.
          </p>
        </div>
      )}

      {phase === "error" && error && (
        <div className="workspace-card">
          <div className="status-banner error">
            <AlertTriangle size={18} />
            <span>{error}</span>
          </div>
          <div className="download-actions">
            {documentId && (
              <button
                className="btn btn-primary"
                onClick={() => runAnalysis(useVlm)}
              >
                <RotateCcw size={14} /> Retry Analysis
              </button>
            )}
            <button className="btn btn-secondary" onClick={reset}>
              Start Over
            </button>
          </div>
        </div>
      )}

      {phase === "done" && result && jobId && (
        <>
          <div className="workspace-card">
            <div className="status-banner success">
              <CheckCircle2 size={18} />
              <span>
                Analysis complete for <strong>{result.filename}</strong> —{" "}
                {result.pages_analyzed} of {result.total_pages} page
                {result.total_pages === 1 ? "" : "s"} in{" "}
                {result.processing_time_seconds.toFixed(1)}s
              </span>
            </div>
          </div>

          {/* 1. Extracted Diagram Information */}
          <section className="workspace-card" id="extracted-info">
            <div className="section-head">
              <h2>Extracted Diagram Information</h2>
              <span className="section-hint">
                {result.findings.length} item
                {result.findings.length === 1 ? "" : "s"} read off the drawing
              </span>
            </div>

            <div className="result-stats">
              <div className="result-stat">
                <span className="num">{result.stats.filled_from_drawing}</span>
                <span className="lbl">Filled From Drawing</span>
              </div>
              <div className="result-stat">
                <span className="num">{result.stats.conflicts}</span>
                <span className="lbl">Conflicts</span>
              </div>
              <div className="result-stat">
                <span className="num">{result.stats.not_detected}</span>
                <span className="lbl">Not Detected</span>
              </div>
            </div>

            {categories.length > 0 && (
              <div className="filter-chips">
                <button
                  className={`chip-filter ${
                    categoryFilter === "all" ? "active" : ""
                  }`}
                  onClick={() => setCategoryFilter("all")}
                >
                  All
                </button>
                {categories.map((c) => (
                  <button
                    key={c}
                    className={`chip-filter ${
                      categoryFilter === c ? "active" : ""
                    }`}
                    onClick={() => setCategoryFilter(c)}
                  >
                    {c}
                  </button>
                ))}
              </div>
            )}

            <div className="table-scroll findings-scroll">
              <table className="data-table findings-table">
                <thead>
                  <tr>
                    <th style={{ width: 52 }}>Page</th>
                    <th style={{ width: 120 }}>Category</th>
                    <th style={{ width: 130 }}>Part No</th>
                    <th style={{ width: 220 }}>Value</th>
                    <th>Detail</th>
                    <th style={{ width: 70 }}>Conf.</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredFindings.map((f, i) => (
                    <tr key={`${f.page_number}-${f.category}-${i}`}>
                      <td className="mono">{f.page_number}</td>
                      <td>
                        <span className="tag">{f.category}</span>
                      </td>
                      <td>{f.part_no || "—"}</td>
                      <td className="mono">{f.value}</td>
                      <td className="detail-cell">{f.detail || "—"}</td>
                      <td>{Math.round(f.confidence * 100)}%</td>
                    </tr>
                  ))}
                  {filteredFindings.length === 0 && (
                    <tr>
                      <td colSpan={6} className="no-data">
                        No extracted information in this category.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {/* 2. Final Report */}
          <section className="workspace-card" id="final-report">
            <div className="section-head">
              <h2>Final Report</h2>
              <span className="section-hint">
                Exactly the columns written to the Excel file
              </span>
            </div>

            <div className="table-scroll">
              <table className="data-table report-table">
                <thead>
                  <tr>
                    {result.table.columns.map((col) => (
                      <th key={col}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.table.rows.map((row) => (
                    <tr key={row.part_no}>
                      {row.values.map((val, idx) => {
                        const col = result.table.columns[idx];
                        const cell = row.cells[col];
                        return (
                          <td
                            key={col}
                            className={cell ? cellClass(cell.status) : ""}
                          >
                            {val}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                  {result.table.rows.length === 0 && (
                    <tr>
                      <td colSpan={result.table.columns.length} className="no-data">
                        No parts were detected on the drawing.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="legend">
              <span>
                <i className="swatch swatch-user" /> As entered by you
              </span>
              <span>
                <i className="swatch swatch-filled" /> Filled in from the drawing
              </span>
              <span>
                <i className="swatch swatch-conflict" /> Differs from the drawing
                (your value kept)
              </span>
              <span>
                <i className="swatch swatch-missing" /> Not detected
              </span>
            </div>
          </section>

          {/* 3. Download */}
          <section className="workspace-card" id="download">
            <div className="section-head">
              <h2>Download</h2>
            </div>
            <div className="download-actions no-margin">
              <a
                href={getPartExcelUrl(jobId)}
                download
                className="btn btn-primary btn-lg"
              >
                <Download size={16} /> Download Analysis (Excel)
              </a>
              <span className="action-hint">
                Four sheets: Report, Traceability, Drawing Information and
                Analysis Log.
              </span>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
