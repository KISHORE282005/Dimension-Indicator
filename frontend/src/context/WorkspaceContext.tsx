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
import {
  getPartProgress,
  getPartResult,
  startPartAnalysis,
  uploadPartReport,
} from "../services/api";
import type { PartReportResult } from "../types";

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
  pageCount: number;
  documentId: string | null;
  jobId: string | null;
  progress: number;
  stage: string;
  detail: string;
  error: string | null;
  result: PartReportResult | null;
  handleFiles: (files: File[]) => void;
  runAnalysis: (useVlm: boolean) => void;
  reset: () => void;
}

const WorkspaceContext = createContext<WorkspaceState | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<WorkspacePhase>("idle");
  const [fileName, setFileName] = useState("");
  const [fileSize, setFileSize] = useState(0);
  const [pageCount, setPageCount] = useState(0);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("");
  const [detail, setDetail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PartReportResult | null>(null);
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
        const res = await uploadPartReport(file);
        setFileName(res.filename);
        setFileSize(res.size_bytes);
        setPageCount(res.page_count);
        setDocumentId(res.document_id);
        setPhase("ready");
        toast.success(
          `${res.filename} uploaded (${res.page_count} page${
            res.page_count === 1 ? "" : "s"
          })`
        );
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
      setStage("queued");
      setDetail("Waiting for a worker...");
      setProgress(0);
      setError(null);

      try {
        const start = await startPartAnalysis(documentId, useVlm, true);
        setJobId(start.job_id);
        stopPolling();
        pollRef.current = window.setInterval(() => {
          getPartProgress(start.job_id)
            .then((p) => {
              setProgress(Math.round(p.progress * 100));
              setStage(p.stage || p.status);
              setDetail(p.detail || "");
              if (p.status === "complete") {
                stopPolling();
                return getPartResult(start.job_id).then((r) => {
                  setResult(r);
                  setProgress(100);
                  setPhase("done");
                  toast.success("Analysis complete!");
                });
              }
              if (p.status === "error") {
                stopPolling();
                setError(p.error || "Analysis failed.");
                setPhase("error");
              }
            })
            .catch(() => {});
        }, 1500);
      } catch (err: any) {
        setError(err.response?.data?.detail || "Could not start the analysis.");
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
    setPageCount(0);
    setDocumentId(null);
    setJobId(null);
    setProgress(0);
    setStage("");
    setDetail("");
    setError(null);
    setResult(null);
  }, [stopPolling]);

  return (
    <WorkspaceContext.Provider
      value={{
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
