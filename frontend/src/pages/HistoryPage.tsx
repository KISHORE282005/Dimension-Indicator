import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { getHistory, deleteAnalysis } from "../services/api";
import type { HistoryItem } from "../types";

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = () => {
    setLoading(true);
    getHistory()
      .then(setItems)
      .catch(() => toast.error("Failed to load history"))
      .finally(() => setLoading(false));
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this analysis?")) return;
    try {
      await deleteAnalysis(id);
      setItems((prev) => prev.filter((i) => i.document_id !== id));
      toast.success("Deleted");
    } catch {
      toast.error("Failed to delete");
    }
  };

  if (loading) {
    return (
      <div className="page loading-page">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="page history-page">
      <h1>Analysis History</h1>
      {items.length === 0 ? (
        <p className="no-data">No analyses yet. Upload a drawing to get started.</p>
      ) : (
        <div className="history-table">
          <table className="data-table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Pages</th>
                <th>Valid</th>
                <th>Issues</th>
                <th>Warnings</th>
                <th>Completed</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.document_id}>
                  <td>
                    <button
                      className="link-btn"
                      onClick={() =>
                        navigate(`/analysis/${item.document_id}`)
                      }
                    >
                      {item.filename}
                    </button>
                  </td>
                  <td>{item.total_pages}</td>
                  <td>
                    <span className={`valid-badge ${item.is_valid ? "valid" : "invalid"}`}>
                      {item.is_valid ? "PASS" : "FAIL"}
                    </span>
                  </td>
                  <td>{item.issues_count}</td>
                  <td>{item.warnings_count}</td>
                  <td>{item.processing_completed || item.created_at}</td>
                  <td>
                    <button
                      className="btn-delete"
                      onClick={() => handleDelete(item.document_id)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
