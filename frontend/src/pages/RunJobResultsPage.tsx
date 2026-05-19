import { Navigate, useParams } from "react-router-dom";

/** Deep link: `/runs/:jobId/results` → dashboard with reports tab. */
export function RunJobResultsPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const id = jobId?.trim();
  if (!id) return <Navigate to="/dashboard" replace />;
  return (
    <Navigate
      to={`/dashboard?job=${encodeURIComponent(id)}&tab=reports`}
      replace
    />
  );
}
