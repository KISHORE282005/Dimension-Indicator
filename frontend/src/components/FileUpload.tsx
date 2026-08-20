import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { uploadFile, analyzeDocument, getProgress } from "../services/api";

export default function FileUpload() {
  const navigate = useNavigate();
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("");
  const [useVlm, setUseVlm] = useState(true);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (acceptedFiles.length === 0) return;
      const file = acceptedFiles[0];

      setUploading(true);
      setStage("Uploading...");
      setProgress(10);

      try {
        const uploadResult = await uploadFile(file);
        setProgress(20);
        setStage("Analyzing...");
        setAnalyzing(true);

        const analyzeResult = await analyzeDocument(
          uploadResult.document_id,
          useVlm
        );

        // Poll progress
        const pollInterval = setInterval(async () => {
          try {
            const prog = await getProgress(uploadResult.document_id);
            setProgress(Math.round(prog.progress * 100));
            setStage(prog.stage);
            if (prog.stage === "complete") {
              clearInterval(pollInterval);
              toast.success("Analysis complete!");
              navigate(`/analysis/${uploadResult.document_id}`);
            } else if (prog.stage === "error") {
              clearInterval(pollInterval);
              toast.error(`Analysis failed: ${prog.error}`);
              setAnalyzing(false);
            }
          } catch {
            // Progress endpoint might not be ready yet
          }
        }, 1000);

        // Auto-navigate after max 120s
        setTimeout(() => {
          clearInterval(pollInterval);
          navigate(`/analysis/${uploadResult.document_id}`);
        }, 120000);
      } catch (err: any) {
        toast.error(err.response?.data?.detail || "Upload failed");
        setUploading(false);
        setAnalyzing(false);
      }
    },
    [useVlm, navigate]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "image/*": [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"],
    },
    maxFiles: 1,
    disabled: uploading || analyzing,
  });

  return (
    <div className="upload-container">
      <div className="upload-header">
        <h1>Engineering Drawing Analysis</h1>
        <p>Upload a PDF or image to extract dimensions, tolerances, GD&T, welding symbols, and more.</p>
      </div>

      <div className="upload-options">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={useVlm}
            onChange={(e) => setUseVlm(e.target.checked)}
            disabled={uploading || analyzing}
          />
          <span>Enable AI Vision Analysis (Gemini 2.5 Pro)</span>
        </label>
      </div>

      <div
        {...getRootProps()}
        className={`dropzone ${isDragActive ? "active" : ""} ${
          uploading || analyzing ? "disabled" : ""
        }`}
      >
        <input {...getInputProps()} />
        {uploading || analyzing ? (
          <div className="upload-progress">
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="progress-text">
              {stage} ({progress}%)
            </p>
          </div>
        ) : (
          <div className="upload-prompt">
            <div className="upload-icon">📄</div>
            <p>
              {isDragActive
                ? "Drop the file here..."
                : "Drag & drop a drawing, or click to select"}
            </p>
            <p className="upload-hint">
              Supports PDF, PNG, JPG, TIFF, BMP, WebP
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
