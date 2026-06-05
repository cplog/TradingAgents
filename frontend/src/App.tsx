import { lazy, type ComponentType } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";

function lazyPage<M extends Record<string, ComponentType<unknown>>, K extends keyof M>(
  factory: () => Promise<M>,
  exportName: K,
) {
  return lazy(() => factory().then((m) => ({ default: m[exportName] })));
}

const BatchPage = lazyPage(() => import("./pages/BatchPage"), "BatchPage");
const DashboardPage = lazyPage(() => import("./pages/DashboardPage"), "DashboardPage");
const HistoryPage = lazyPage(() => import("./pages/HistoryPage"), "HistoryPage");
const HistoryStatsPage = lazyPage(() => import("./pages/HistoryStatsPage"), "HistoryStatsPage");
const MonitorPage = lazyPage(() => import("./pages/MonitorPage"), "MonitorPage");
const NewsPage = lazyPage(() => import("./pages/NewsPage"), "NewsPage");
const RunDetailPage = lazyPage(() => import("./pages/RunDetailPage"), "RunDetailPage");
const RunJobResultsPage = lazyPage(() => import("./pages/RunJobResultsPage"), "RunJobResultsPage");
const ScreenerPage = lazyPage(() => import("./pages/ScreenerPage"), "ScreenerPage");
const SectorIndustryPage = lazyPage(() => import("./pages/SectorIndustryPage"), "SectorIndustryPage");
const StockPage = lazyPage(() => import("./pages/StockPage"), "StockPage");
const SystemPage = lazyPage(() => import("./pages/SystemPage"), "SystemPage");
const TopicDetailPage = lazyPage(() => import("./pages/TopicDetailPage"), "TopicDetailPage");
const TopicsPage = lazyPage(() => import("./pages/TopicsPage"), "TopicsPage");
const WatchlistPage = lazyPage(() => import("./pages/WatchlistPage"), "WatchlistPage");

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
