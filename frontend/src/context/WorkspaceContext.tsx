import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import toast from "react-hot-toast";
import { analyzeDocument, getProgress, uploadFile } from "../services/api";
import type { AnalyzeResponse } from "../types";

export type WorkspacePhase =
  | "idle"
  | "uploading"
  | "ready"
  | "analyzing"
  | "done"
  | "error";

interface WorkspaceState {
  phase: WorkspacePhase;
  fileName: string;
  fileSize: number;
  documentId: string | null;
  progress: number;
  stage: string;
  error: string | null;
  result: AnalyzeResponse | null;
  handleFiles: (files: File[]) => void;
  runAnalysis: (useVlm: boolean) => void;
  reset: () => void;
}

const WorkspaceContext = createContext<WorkspaceState | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<WorkspacePhase>("idle");
  const [fileName, setFileName] = useState("");
  const [fileSize, setFileSize] = useState(0);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current !== null) window.clearInterval(pollRef.current);
    };
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const handleFiles = useCallback(
    async (files: File[]) => {
      if (!files.length) return;
      stopPolling();
      const file = files[0];
      setPhase("uploading");
      setStage("Uploading drawing...");
      setError(null);
      setResult(null);
      try {
        const res = await uploadFile(file);
        setFileName(res.filename);
        setFileSize(res.file_size);
        setDocumentId(res.document_id);
        setPhase("ready");
        toast.success(`${res.filename} uploaded`);
      } catch (err: any) {
        setError(err.response?.data?.detail || "Upload failed. Please try again.");
        setPhase("error");
      }
    },
    [stopPolling]
  );

  const runAnalysis = useCallback(
    async (useVlm: boolean) => {
      if (!documentId) return;
      setPhase("analyzing");
      setStage("Starting analysis...");
      setProgress(2);
      setError(null);

      // Best-effort progress polling; the analyze endpoint blocks until the
      // pipeline finishes, so polls may only resolve at the end.
      pollRef.current = window.setInterval(() => {
        getProgress(documentId)
          .then((p) => {
            setProgress(Math.max(2, Math.round(p.progress * 100)));
            if (p.stage && p.stage !== "unknown") setStage(p.stage);
          })
          .catch(() => {});
      }, 1500);

      try {
        const res = await analyzeDocument(documentId, useVlm);
        stopPolling();
        setResult(res);
        setProgress(100);
        setStage("complete");
        setPhase("done");
        toast.success("Analysis complete!");
      } catch (err: any) {
        stopPolling();
        setError(err.response?.data?.detail || "Analysis failed. Please try again.");
        setPhase("error");
      }
    },
    [documentId, stopPolling]
  );

  const reset = useCallback(() => {
    stopPolling();
    setPhase("idle");
    setFileName("");
    setFileSize(0);
    setDocumentId(null);
    setProgress(0);
    setStage("");
    setError(null);
    setResult(null);
  }, [stopPolling]);

  return (
    <WorkspaceContext.Provider
      value={{
        phase,
        fileName,
        fileSize,
        documentId,
        progress,
        stage,
        error,
        result,
        handleFiles,
        runAnalysis,
        reset,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceState {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return ctx;
}
