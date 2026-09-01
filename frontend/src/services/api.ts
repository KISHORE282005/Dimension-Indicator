import axios from "axios";
import type {
  UploadResponse,
  AnalyzeResponse,
  DocumentAnalysisResult,
  ExtractedItem,
  DetectedIssue,
  ValidationResult,
  HistoryItem,
  PartUploadResponse,
  PartAnalyzeResponse,
  PartJobProgress,
  PartReportResult,
} from "../types";

const api = axios.create({ baseURL: "/api" });

// ---------------------------------------------------------------------------
// Part report workflow (fixed 10-column Excel format)
// ---------------------------------------------------------------------------

export const uploadPartReport = async (
  files: File[]
): Promise<PartUploadResponse> => {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  const { data } = await api.post<PartUploadResponse>(
    "/part-report/upload",
    formData
  );
  return data;
};

export const startPartAnalysis = async (
  documentId: string,
  useVlm = true,
  useOcr = true
): Promise<PartAnalyzeResponse> => {
  const { data } = await api.post<PartAnalyzeResponse>("/part-report/analyze", {
    document_id: documentId,
    parts: [],
    use_vlm: useVlm,
    use_ocr: useOcr,
  });
  return data;
};

export const getPartProgress = async (
  jobId: string
): Promise<PartJobProgress> => {
  const { data } = await api.get<PartJobProgress>(
    `/part-report/progress/${jobId}`
  );
  return data;
};

export const getPartResult = async (
  jobId: string
): Promise<PartReportResult> => {
  const { data } = await api.get<PartReportResult>(`/part-report/result/${jobId}`);
  return data;
};

export const getPartExcelUrl = (jobId: string) =>
  `/api/part-report/excel/${jobId}`;

export const updatePartCells = async (
  jobId: string,
  edits: { part_no: string; column: string; value: string }[]
): Promise<{ job_id: string; applied: number }> => {
  const { data } = await api.post(`/part-report/edit/${jobId}`, edits);
  return data;
};

export const uploadFile = async (file: File): Promise<UploadResponse> => {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<UploadResponse>("/upload", formData);
  return data;
};

export const analyzeDocument = async (
  documentId: string,
  useVlm = true,
  ocrMinConfidence = 0.3
): Promise<AnalyzeResponse> => {
  const { data } = await api.post<AnalyzeResponse>(
    `/analyze/${documentId}?use_vlm=${useVlm}&ocr_min_confidence=${ocrMinConfidence}`
  );
  return data;
};

export const getProgress = async (
  documentId: string
): Promise<{ stage: string; progress: number; error?: string }> => {
  const { data } = await api.get(`/progress/${documentId}`);
  return data;
};

export const getResults = async (
  documentId: string
): Promise<DocumentAnalysisResult> => {
  const { data } = await api.get(`/results/${documentId}`);
  return data;
};

export const getSummary = async (
  documentId: string
): Promise<{
  document_id: string;
  filename: string;
  total_pages: number;
  summary: Record<string, number>;
  is_valid: boolean | null;
  processing_time: number;
}> => {
  const { data } = await api.get(`/results/${documentId}/summary`);
  return data;
};

export const getPageResult = async (
  documentId: string,
  pageNumber: number
) => {
  const { data } = await api.get(`/results/${documentId}/page/${pageNumber}`);
  return data;
};

export const getItems = async (
  documentId: string,
  params?: {
    category?: string;
    page?: number;
    min_confidence?: number;
  }
): Promise<ExtractedItem[]> => {
  const { data } = await api.get(`/results/${documentId}/items`, { params });
  return data;
};

export const getIssues = async (
  documentId: string,
  severity?: string
): Promise<DetectedIssue[]> => {
  const { data } = await api.get(`/results/${documentId}/issues`, {
    params: severity ? { severity } : {},
  });
  return data;
};

export const getValidation = async (
  documentId: string
): Promise<ValidationResult> => {
  const { data } = await api.get(`/results/${documentId}/validation`);
  return data;
};

export const getJsonExport = async (
  documentId: string
): Promise<DocumentAnalysisResult> => {
  const { data } = await api.get(`/results/${documentId}/json`);
  return data;
};

export const getHistory = async (limit = 50): Promise<HistoryItem[]> => {
  const { data } = await api.get("/history", { params: { limit } });
  return data;
};

export const deleteAnalysis = async (documentId: string): Promise<void> => {
  await api.delete(`/history/${documentId}`);
};

export const getPdfUrl = (documentId: string) =>
  `/api/reports/${documentId}/pdf`;

export const getExcelUrl = (documentId: string) =>
  `/api/reports/${documentId}/excel`;

export const getPageImageUrl = (documentId: string, pageNumber: number) =>
  `/api/pages/${documentId}/${pageNumber}`;

export const getHealth = async () => {
  const { data } = await api.get("/health");
  return data;
};
