import {
  fetchHistoryRun,
  getJob,
  resumeJob,
  submitAnalyze,
  type AnalyzeRequestBody,
} from "../api";
import type { HistoryTableRow } from "./historyDisplay";
import {
  buildRerunAnalyzePayload,
  buildRerunAnalyzePayloadFromJob,
} from "./historyRerun";

export type RetryFailedResult =
  | { action: "resumed"; jobId: string }
  | { action: "submitted"; jobId: string; newJobId: string };

export async function buildRetryAnalyzeBody(jobId: string): Promise<AnalyzeRequestBody> {
  const job = await getJob(jobId);
  try {
    const detail = await fetchHistoryRun(jobId);
    const body = buildRerunAnalyzePayload(detail);
    if (job.trigger === "scan" || job.trigger === "overnight_monitor") {
      body.mode = "scan";
    }
    return body;
  } catch {
    return buildRerunAnalyzePayloadFromJob(job);
  }
}

/** Resume checkpointed failure or submit a fresh analysis with prior settings. */
export async function retryFailedRun(row: HistoryTableRow): Promise<RetryFailedResult> {
  const jobId = (row.job_id ?? row.run_id).trim();
  if (!jobId) {
    throw new Error("Missing job id");
  }

  const job = await getJob(jobId);
  if (job.status !== "failed") {
    throw new Error(`Job ${jobId} is ${job.status}, not failed`);
  }

  if (job.resumable) {
    await resumeJob(jobId);
    return { action: "resumed", jobId };
  }

  const body = await buildRetryAnalyzeBody(jobId);
  const created = await submitAnalyze(body);
  return { action: "submitted", jobId, newJobId: created.job_id };
}

export type BulkRetrySummary = {
  resumed: number;
  submitted: number;
  errors: { jobId: string; message: string }[];
};

export async function retryAllFailedRuns(rows: HistoryTableRow[]): Promise<BulkRetrySummary> {
  const failed = rows.filter((r) => r.job_status === "failed");
  const summary: BulkRetrySummary = { resumed: 0, submitted: 0, errors: [] };

  for (const row of failed) {
    const jobId = (row.job_id ?? row.run_id).trim();
    try {
      const result = await retryFailedRun(row);
      if (result.action === "resumed") summary.resumed += 1;
      else summary.submitted += 1;
    } catch (e: unknown) {
      summary.errors.push({
        jobId,
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }

  return summary;
}
