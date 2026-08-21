import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  Play,
  RotateCcw,
} from "lucide-react";
import { useWorkspace } from "../context/WorkspaceContext";
import { getExcelUrl, getPdfUrl } from "../services/api";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function prettyLabel(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function UploadPage() {
  const navigate = useNavigate();
  const {
    phase,
    fileName,
    fileSize,
    documentId,
    progress,
    stage,
    error,
    result,
    runAnalysis,
    reset,
  } = useWorkspace();
  const [useVlm, setUseVlm] = useState(true);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (phase !== "analyzing") {
      setElapsed(0);
      return;
    }
    const t = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, [phase]);

  const summaryEntries = Object.entries(result?.summary ?? {})
    .filter(([, v]) => v > 0)
    .slice(0, 8);

  return (
    <div className="page upload-page">
      <header className="page-header">
        <h1>Engineering Drawing Analysis</h1>
        <p>
          Upload an engineering diagram to automatically extract dimensions,
          tolerances, GD&amp;T callouts, holes, welding symbols, BOM data and
          more — then download the full analysis report.
        </p>
      </header>

      {phase === "idle" && (
        <div className="feature-grid">
          <div className="workspace-card feature-card">
            <span className="feature-num">1</span>
            <h3>Upload</h3>
            <p>
              Drag &amp; drop your drawing into the sidebar — PDF or image,
              single or multi-page.
            </p>
          </div>
          <div className="workspace-card feature-card">
            <span className="feature-num">2</span>
            <h3>Analyze</h3>
            <p>
              OCR and AI vision read every page and extract dimensions,
              tolerances, GD&amp;T and notes.
            </p>
          </div>
          <div className="workspace-card feature-card">
            <span className="feature-num">3</span>
            <h3>Download</h3>
            <p>
              Review the summary here and download the complete analysis report
              as Excel or PDF.
            </p>
          </div>
        </div>
      )}

      {phase === "uploading" && (
        <div className="workspace-card status-card">
          <Loader2 size={22} className="spin" />
          <div>
            <h3>Uploading drawing...</h3>
            <p>{stage}</p>
          </div>
        </div>
      )}

      {phase === "ready" && (
        <div className="workspace-card">
          <div className="file-ready-row">
            <FileText size={26} className="file-icon" />
            <div className="file-info">
              <strong>{fileName}</strong>
              <span>{formatSize(fileSize)} &middot; ready to analyze</span>
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
            <span>Enable AI Vision Analysis (Gemini 2.5 Pro)</span>
          </label>

          <div className="analyze-actions">
            <button
              className="btn btn-primary btn-lg"
              onClick={() => runAnalysis(useVlm)}
            >
              <Play size={16} /> Run Analysis
            </button>
            <span className="action-hint">
              Extraction runs on every page of the document.
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
                {stage || "Processing"} &middot; {elapsed}s elapsed
              </span>
            </div>
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

      {phase === "done" && result && documentId && (
        <>
          <div className="workspace-card">
            <div className="status-banner success">
              <CheckCircle2 size={18} />
              <span>
                Analysis complete for <strong>{result.filename}</strong> —{" "}
                {result.total_pages} page{result.total_pages === 1 ? "" : "s"} in{" "}
                {result.processing_time.toFixed(1)}s
                {result.is_valid === true && " · validation passed"}
                {result.is_valid === false &&
                  ` · ${result.issues_count} issue${
                    result.issues_count === 1 ? "" : "s"
                  } flagged`}
              </span>
            </div>

            {summaryEntries.length > 0 && (
              <div className="result-stats">
                {summaryEntries.map(([key, count]) => (
                  <div key={key} className="result-stat">
                    <span className="num">{count}</span>
                    <span className="lbl">{prettyLabel(key)}</span>
                  </div>
                ))}
              </div>
            )}

            <div className="download-actions">
              <a
                href={getExcelUrl(documentId)}
                download
                className="btn btn-primary btn-lg"
              >
                <Download size={16} /> Download Analysis
              </a>
              <a
                href={getPdfUrl(documentId)}
                download
                className="btn btn-secondary"
              >
                <FileText size={15} /> PDF Report
              </a>
              <Link
                to={`/analysis/${documentId}`}
                className="btn btn-secondary"
              >
                View Full Report
              </Link>
              <button className="btn btn-ghost" onClick={reset}>
                <RotateCcw size={14} /> New Upload
              </button>
            </div>
          </div>
        </>
      )}

      {phase === "error" && error && (
        <div className="workspace-card">
          <div className="status-banner error">
            <AlertTriangle size={18} />
            <span>{error}</span>
          </div>
          <div className="download-actions">
            {documentId ? (
              <button
                className="btn btn-primary"
                onClick={() => runAnalysis(useVlm)}
              >
                <RotateCcw size={14} /> Retry Analysis
              </button>
            ) : null}
            <button className="btn btn-secondary" onClick={reset}>
              Start Over
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
