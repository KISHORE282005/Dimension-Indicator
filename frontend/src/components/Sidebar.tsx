import { Link, useLocation, useNavigate } from "react-router-dom";
import type { MouseEvent } from "react";
import {
  Download,
  FileSearch,
  History,
  Ruler,
  Table2,
  UploadCloud,
} from "lucide-react";
import { useWorkspace } from "../context/WorkspaceContext";

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { phase, fileName, progress, reset } = useWorkspace();

  const busy = phase === "uploading" || phase === "analyzing";
  const done = phase === "done";

  const goToSection = (id: string) => {
    if (location.pathname !== "/") navigate("/");
    window.setTimeout(() => {
      document.getElementById(id)?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 80);
  };

  const startNewUpload = () => {
    reset();
    if (location.pathname !== "/") navigate("/");
    window.setTimeout(() => window.scrollTo({ top: 0, behavior: "smooth" }), 80);
  };

  // Once a run has finished (or failed), "Upload" must always land on a clean
  // upload screen - never on the stale results. Only an in-flight upload or a
  // running analysis keeps the current session alive.
  const handleNavUpload = (e: MouseEvent) => {
    if (busy || phase === "idle") return;
    e.preventDefault();
    startNewUpload();
  };

  return (
    <aside className="app-sidebar">
      <div className="sidebar-brand">
        <span className="brand-icon">
          <Ruler size={22} />
        </span>
        <div>
          <div className="brand-name">Dimension Indicator</div>
          <div className="brand-sub">Drawing Analysis Suite</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        <Link
          to="/"
          className={location.pathname === "/" ? "active" : ""}
          onClick={handleNavUpload}
        >
          <UploadCloud size={16} /> Upload
        </Link>
        <Link
          to="/history"
          className={location.pathname === "/history" ? "active" : ""}
        >
          <History size={16} /> History
        </Link>
      </nav>

      <div className="sidebar-upload">
        <button
          className="sidebar-upload-btn"
          onClick={startNewUpload}
          disabled={busy}
        >
          <UploadCloud size={18} />
          Upload Engineering Diagram
        </button>

        {!busy && fileName && (
          <p className="sidebar-note">
            Current file: <strong>{fileName}</strong>
          </p>
        )}

        <p className="sidebar-note">
          Multi-page PDFs are processed page by page — no page is skipped.
        </p>
      </div>

      {done && (
        <nav className="sidebar-nav results-nav">
          <span className="nav-group-label">Analysis Results</span>
          <button onClick={() => goToSection("extracted-info")}>
            <FileSearch size={16} /> Extracted Diagram Information
          </button>
          <button onClick={() => goToSection("final-report")}>
            <Table2 size={16} /> Final Report
          </button>
          <button onClick={() => goToSection("download")}>
            <Download size={16} /> Download
          </button>
        </nav>
      )}

      {phase === "analyzing" && (
        <div className="sidebar-progress-wrap">
          <span className="nav-group-label">Analyzing… {progress}%</span>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}

      <div className="sidebar-footer">
        AI-powered extraction of dimensions, tolerances, GD&amp;T and more.
      </div>
    </aside>
  );
}
