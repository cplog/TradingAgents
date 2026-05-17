import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AdminPage } from "./pages/AdminPage";
import { BatchPage } from "./pages/BatchPage";
import { DashboardPage } from "./pages/DashboardPage";
import { HistoryPage } from "./pages/HistoryPage";
import { NewsPage } from "./pages/NewsPage";
import { ScreenerPage } from "./pages/ScreenerPage";
import { SectorIndustryPage } from "./pages/SectorIndustryPage";
import { SystemPage } from "./pages/SystemPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/batch" element={<BatchPage />} />
        <Route path="/screener" element={<ScreenerPage />} />
        <Route path="/sectors" element={<SectorIndustryPage />} />
        <Route path="/news" element={<NewsPage />} />
        <Route path="/system" element={<SystemPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
