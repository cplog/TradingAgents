import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { BatchPage } from "./pages/BatchPage";
import { DashboardPage } from "./pages/DashboardPage";
import { HistoryPage } from "./pages/HistoryPage";
import { HistoryStatsPage } from "./pages/HistoryStatsPage";
import { NewsPage } from "./pages/NewsPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { RunJobResultsPage } from "./pages/RunJobResultsPage";
import { StockPage } from "./pages/StockPage";
import { ScreenerPage } from "./pages/ScreenerPage";
import { SectorIndustryPage } from "./pages/SectorIndustryPage";
import { SystemPage } from "./pages/SystemPage";
import { MonitorPage } from "./pages/MonitorPage";
import { TopicsPage } from "./pages/TopicsPage";
import { TopicDetailPage } from "./pages/TopicDetailPage";
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
        <Route path="/topics" element={<TopicsPage />} />
        <Route path="/topics/:topicId" element={<TopicDetailPage />} />
        <Route path="/watchlists" element={<WatchlistPage />} />
        <Route path="/monitor" element={<MonitorPage />} />
        <Route path="/system" element={<SystemPage />} />
        <Route path="/settings" element={<Navigate to="/system" replace />} />
        <Route path="/configure" element={<Navigate to="/dashboard" replace />} />
        <Route path="/runs/:jobId" element={<RunDetailPage />} />
        <Route path="/runs/:jobId/results" element={<RunJobResultsPage />} />
        <Route path="/stocks/:ticker" element={<StockPage />} />
        <Route path="/admin" element={<Navigate to="/system" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
