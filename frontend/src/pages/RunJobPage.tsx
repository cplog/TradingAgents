import { Navigate, useParams } from "react-router-dom";

/** Deep link: `/runs/:jobId` → dashboard job loader (`?job=`). */
export function RunJobPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const id = jobId?.trim();
  if (!id) return <Navigate to="/dashboard" replace />;
  return <Navigate to={`/dashboard?job=${encodeURIComponent(id)}`} replace />;
}
