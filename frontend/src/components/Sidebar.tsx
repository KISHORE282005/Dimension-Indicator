import { Link, useLocation, useNavigate } from "react-router-dom";
import { History, Ruler, UploadCloud } from "lucide-react";
import { useWorkspace } from "../context/WorkspaceContext";

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { phase, fileName } = useWorkspace();

  const busy = phase === "uploading" || phase === "analyzing";

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
        <Link to="/" className={location.pathname === "/" ? "active" : ""}>
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
          onClick={() => navigate("/")}
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

      <div className="sidebar-footer">
        AI-powered extraction of dimensions, tolerances, GD&amp;T and more.
      </div>
    </aside>
  );
}
