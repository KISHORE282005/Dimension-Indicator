import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  FileText,
  History,
  Ruler,
  UploadCloud,
} from "lucide-react";
import { useWorkspace } from "../context/WorkspaceContext";

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { phase, handleFiles, fileName, progress, stage } = useWorkspace();

  const busy = phase === "uploading" || phase === "analyzing";

  const onDrop = useCallback(
    (files: File[]) => {
      handleFiles(files);
      navigate("/");
    },
    [handleFiles, navigate]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "image/*": [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"],
    },
    maxFiles: 1,
    multiple: false,
    disabled: busy,
  });

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
        <h3>
          <FileText size={14} /> Upload Engineering Diagram
        </h3>
        <div
          {...getRootProps()}
          className={`sidebar-dropzone ${isDragActive ? "active" : ""} ${
            busy ? "disabled" : ""
          }`}
          aria-label="Upload an engineering diagram"
        >
          <input {...getInputProps()} />
          <UploadCloud size={28} strokeWidth={1.6} />
          <div className="sd-text">
            {isDragActive ? "Drop the file here..." : "Drag & drop or click to browse"}
          </div>
          <div className="sd-hint">PDF, JPG, PNG, TIFF, BMP, WebP</div>
        </div>

        {busy && (
          <div className="sidebar-progress">
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${progress}%` }} />
            </div>
            <span className="sidebar-progress-text">{stage || "Working..."}</span>
          </div>
        )}

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
