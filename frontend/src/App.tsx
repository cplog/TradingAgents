import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AdminPage } from "./pages/AdminPage";
import { BatchPage } from "./pages/BatchPage";
import { DashboardPage } from "./pages/DashboardPage";
import { HistoryPage } from "./pages/HistoryPage";
import { HistoryStatsPage } from "./pages/HistoryStatsPage";
import { NewsPage } from "./pages/NewsPage";
import { RunJobPage } from "./pages/RunJobPage";
import { RunJobResultsPage } from "./pages/RunJobResultsPage";
import { ScreenerPage } from "./pages/ScreenerPage";
import { SectorIndustryPage } from "./pages/SectorIndustryPage";
import { SystemPage } from "./pages/SystemPage";
import { WatchlistPage } from "./pages/WatchlistPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/history/stats" element={<HistoryStatsPage />} />
        <Route path="/batch" element={<BatchPage />} />
        <Route path="/screener" element={<ScreenerPage />} />
        <Route path="/sectors" element={<SectorIndustryPage />} />
        <Route path="/news" element={<NewsPage />} />
        <Route path="/watchlists" element={<WatchlistPage />} />
        <Route path="/system" element={<SystemPage />} />
        <Route path="/settings" element={<Navigate to="/system" replace />} />
        <Route path="/configure" element={<Navigate to="/dashboard" replace />} />
        <Route path="/runs/:jobId" element={<RunJobPage />} />
        <Route path="/runs/:jobId/results" element={<RunJobResultsPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
