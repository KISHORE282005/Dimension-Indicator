import axios from "axios";
import type {
  UploadResponse,
  AnalyzeResponse,
  DocumentAnalysisResult,
  ExtractedItem,
  DetectedIssue,
  ValidationResult,
  HistoryItem,
} from "../types";

const api = axios.create({ baseURL: "/api" });

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
