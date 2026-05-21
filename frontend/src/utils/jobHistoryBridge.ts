import type { HistoryRunDetail, JobResultPayload, JobStatus } from "../api";

/** Hydrate live job state from a persisted History run (worker TTL expired). */
export function historyRunToJobStatus(detail: HistoryRunDetail): JobStatus {
  const completedAt = detail.completed_at ?? new Date().toISOString();
  const result: JobResultPayload = {
    ticker: detail.ticker,
    date: detail.date,
    rating: detail.rating,
    confidence: detail.confidence,
    reports: detail.reports ?? {},
    analyst_coverage: detail.analyst_coverage ?? null,
    structured: detail.structured ?? null,
    artifacts_path: detail.artifacts_path ?? null,
    completed_at: completedAt,
    dimensions: detail.dimensions ?? null,
    dimensions_commentary: detail.dimensions_commentary ?? null,
    dimensions_error: detail.dimensions_error ?? null,
    dimensions_in_graph: detail.dimensions_in_graph ?? null,
  };
  return {
    job_id: detail.job_id || detail.run_id,
    status: "completed",
    created_at: detail.created_at ?? completedAt,
    ticker: detail.ticker,
    date: detail.date,
    result,
    error: null,
    progress_events: [],
    batch_id: detail.batch_id ?? null,
    provenance: detail.provenance ?? null,
  };
}
