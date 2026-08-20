import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import toast from "react-hot-toast";
import {
  getResults,
  getPdfUrl,
  getExcelUrl,
  getPageImageUrl,
} from "../services/api";
import ExtractionSummary from "../components/ExtractionSummary";
import DimensionTable from "../components/DimensionTable";
import DimensionControlList from "../components/DimensionControlList";
import {
  HoleTable,
  WeldingTable,
  GDTTable,
  SurfaceFinishTable,
  BOMTable,
  NotesList,
  DatumsTable,
  MaterialsTable,
} from "../components/ItemsTable";
import IssuesPanel from "../components/IssuesPanel";
import AIInterpretationPanel from "../components/AIInterpretationPanel";
import JsonInspector from "../components/JsonInspector";
import type { DocumentAnalysisResult, PageResult, DimensionControlRow, DimensionItem, HoleItem, ToleranceItem } from "../types";

type TabId =
  | "dcl"
  | "summary"
  | "dimensions"
  | "holes"
  | "welding"
  | "gdt"
  | "surface"
  | "bom"
  | "notes"
  | "datums"
  | "materials"
  | "ai"
  | "issues"
  | "json";

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: "dcl", label: "Dimension Control List", icon: "📋" },
  { id: "summary", label: "Summary", icon: "📊" },
  { id: "dimensions", label: "Dimensions", icon: "📏" },
  { id: "holes", label: "Holes", icon: "🔩" },
  { id: "welding", label: "Welding", icon: "🔥" },
  { id: "gdt", label: "GD&T", icon: "📐" },
  { id: "surface", label: "Surface", icon: "✨" },
  { id: "bom", label: "BOM", icon: "📦" },
  { id: "notes", label: "Notes", icon: "📝" },
  { id: "datums", label: "Datums", icon: "📍" },
  { id: "materials", label: "Materials", icon: "🧱" },
  { id: "ai", label: "AI Analysis", icon: "🤖" },
  { id: "issues", label: "Issues", icon: "⚠️" },
  { id: "json", label: "JSON", icon: "📋" },
];

export default function AnalysisPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const [data, setData] = useState<DocumentAnalysisResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabId>("summary");
  const [selectedPage, setSelectedPage] = useState<number>(1);

  useEffect(() => {
    if (!documentId) return;
    setLoading(true);
    getResults(documentId)
      .then((result) => {
        setData(result);
        setLoading(false);
      })
      .catch((err) => {
        toast.error("Failed to load results");
        setLoading(false);
      });
  }, [documentId]);

  if (loading) {
    return (
      <div className="page loading-page">
        <div className="spinner" />
        <p>Loading analysis results...</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="page error-page">
        <p>No results found for this document.</p>
      </div>
    );
  }

  const currentPage: PageResult | undefined = data.page_results.find(
    (pr) => pr.page_number === selectedPage
  );

  return (
    <div className="page analysis-page">
      <div className="analysis-header">
        <div className="header-info">
          <h1>{data.filename}</h1>
          <p>
            {data.total_pages} pages &middot;{" "}
            {data.total_processing_time_seconds.toFixed(1)}s
          </p>
        </div>
        <div className="header-actions">
          <a
            href={getPdfUrl(documentId!)}
            className="btn btn-primary"
            download
          >
            📄 PDF Report
          </a>
          <a
            href={getExcelUrl(documentId!)}
            className="btn btn-secondary"
            download
          >
            📊 Excel Report
          </a>
        </div>
      </div>

      <div className="analysis-layout">
        <div className="sidebar">
          <div className="page-selector">
            <label>Page:</label>
            <select
              value={selectedPage}
              onChange={(e) => setSelectedPage(Number(e.target.value))}
            >
              {data.page_results.map((pr) => (
                <option key={pr.page_number} value={pr.page_number}>
                  Page {pr.page_number}
                </option>
              ))}
            </select>
          </div>

          {documentId && (
            <div className="page-preview">
              <img
                src={getPageImageUrl(documentId, selectedPage)}
                alt={`Page ${selectedPage}`}
                loading="lazy"
              />
            </div>
          )}

          <div className="tab-nav">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                className={`tab-btn ${activeTab === tab.id ? "active" : ""}`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.icon} {tab.label}
              </button>
            ))}
          </div>
        </div>

        <div className="content-area">
          {activeTab === "dcl" && (
            <DimensionControlList
              rows={data.consolidated_dimension_control || []}
              allDimensions={data.page_results.flatMap((pr) => pr.dimensions)}
              allHoles={data.page_results.flatMap((pr) => pr.holes)}
              allTolerances={data.page_results.flatMap((pr) => pr.tolerances)}
            />
          )}

          {activeTab === "summary" && (
            <ExtractionSummary
              summary={data.extraction_summary}
              totalPages={data.total_pages}
              isValid={data.validation_result?.is_valid ?? null}
              processingTime={data.total_processing_time_seconds}
            />
          )}

          {activeTab === "dimensions" && (
            <DimensionTable
              items={data.page_results.flatMap((pr) => pr.dimensions)}
            />
          )}

          {activeTab === "holes" && (
            <HoleTable
              items={data.page_results.flatMap((pr) => pr.holes)}
            />
          )}

          {activeTab === "welding" && (
            <WeldingTable
              items={data.page_results.flatMap((pr) => pr.welding_items)}
            />
          )}

          {activeTab === "gdt" && (
            <GDTTable
              items={data.page_results.flatMap((pr) => pr.gd_t_items)}
            />
          )}

          {activeTab === "surface" && (
            <SurfaceFinishTable
              items={data.page_results.flatMap((pr) => pr.surface_finishes)}
            />
          )}

          {activeTab === "bom" && (
            <BOMTable
              items={data.page_results.flatMap((pr) => pr.bom_items)}
            />
          )}

          {activeTab === "notes" && (
            <NotesList
              items={data.page_results.flatMap((pr) => pr.manufacturing_notes)}
            />
          )}

          {activeTab === "datums" && (
            <DatumsTable
              items={data.page_results.flatMap((pr) => pr.datums)}
            />
          )}

          {activeTab === "materials" && (
            <MaterialsTable
              items={data.page_results.flatMap((pr) => pr.materials)}
            />
          )}

          {activeTab === "ai" && (
            <AIInterpretationPanel
              interpretations={data.page_results.flatMap(
                (pr) => pr.ai_interpretations
              )}
            />
          )}

          {activeTab === "issues" && (
            <IssuesPanel
              validation={data.validation_result}
              issues={data.all_issues}
            />
          )}

          {activeTab === "json" && <JsonInspector data={data} />}
        </div>
      </div>
    </div>
  );
}
