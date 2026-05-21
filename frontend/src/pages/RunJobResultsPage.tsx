import { Navigate, useParams } from "react-router-dom";

/** Deep link: `/runs/:jobId/results` → run page with reports tab pre-selected. */
export function RunJobResultsPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const id = jobId?.trim();
  if (!id) return <Navigate to="/dashboard" replace />;
  return (
    <Navigate
      to={`/runs/${encodeURIComponent(id)}?tab=reports`}
      replace
    />
  );
}
