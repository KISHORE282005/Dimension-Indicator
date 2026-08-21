import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import UploadPage from "./pages/UploadPage";
import AnalysisPage from "./pages/AnalysisPage";
import HistoryPage from "./pages/HistoryPage";
import Sidebar from "./components/Sidebar";
import { WorkspaceProvider } from "./context/WorkspaceContext";

export default function App() {
  return (
    <BrowserRouter>
      <WorkspaceProvider>
        <Toaster position="top-right" />
        <div className="app-shell">
          <Sidebar />
          <div className="app-main">
            <main className="main-content">
              <Routes>
                <Route path="/" element={<UploadPage />} />
                <Route path="/analysis/:documentId" element={<AnalysisPage />} />
                <Route path="/history" element={<HistoryPage />} />
              </Routes>
            </main>
          </div>
        </div>
      </WorkspaceProvider>
    </BrowserRouter>
  );
}
