import type { JobStatus } from "../api";
import { buildPipelineNodeRows } from "./pipelineProgress";

const STATUS_RANK: Record<string, number> = {
  running: 0,
  resuming: 0,
  queued: 1,
  pending: 1,
};

function parseTs(s: string | undefined | null): number {
  if (!s) return 0;
  const t = Date.parse(s);
  return Number.isFinite(t) ? t : 0;
}

/** Running/resuming first, then queued; within each group oldest-first (FIFO / surface long runners). */
export function sortActiveJobs(jobs: JobStatus[]): JobStatus[] {
  return [...jobs].sort((a, b) => {
    const ra = STATUS_RANK[a.status.toLowerCase()] ?? 2;
    const rb = STATUS_RANK[b.status.toLowerCase()] ?? 2;
    if (ra !== rb) return ra - rb;
    return parseTs(a.created_at) - parseTs(b.created_at);
  });
}

export function partitionActiveJobs(jobs: JobStatus[]): {
  running: JobStatus[];
  queued: JobStatus[];
} {
  const sorted = sortActiveJobs(jobs);
  const running: JobStatus[] = [];
  const queued: JobStatus[] = [];
  for (const job of sorted) {
    const s = job.status.toLowerCase();
    if (s === "running" || s === "resuming") running.push(job);
    else queued.push(job);
  }
  return { running, queued };
}

export function formatElapsedSince(iso: string | null | undefined, nowMs = Date.now()): string {
  if (!iso) return "";
  const ms = nowMs - Date.parse(iso);
  if (!Number.isFinite(ms) || ms < 0) return "";
  const total = Math.floor(ms / 1000);
  if (total < 60) return `${total}s`;
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (m < 60) return `${m}m ${s.toString().padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  if (h < 24) return rm > 0 ? `${h}h ${rm}m` : `${h}h`;
  const d = Math.floor(h / 24);
  const rh = h % 24;
  return rh > 0 ? `${d}d ${rh}h` : `${d}d`;
}

/**
 * ISO timestamp for the jobs ribbon elapsed badge.
 * Queued jobs: since submit (created_at). Running/resuming: since this execution
 * started (first running event after the latest queued), not total queue+run time.
 */
export function jobElapsedAnchorIso(job: JobStatus): string | null | undefined {
  const status = job.status.toLowerCase();
  if (status === "queued" || status === "pending") {
    return job.created_at;
  }
  if (status === "running" || status === "resuming") {
    const events = job.progress_events ?? [];
    let lastQueuedIdx = -1;
    for (let i = 0; i < events.length; i += 1) {
      if (events[i]?.stage?.toLowerCase() === "queued") lastQueuedIdx = i;
    }
    for (let i = lastQueuedIdx + 1; i < events.length; i += 1) {
      const e = events[i];
      if (e?.stage?.toLowerCase() === "running" && e.ts) return e.ts;
    }
    for (const e of events) {
      if (e?.stage?.toLowerCase() === "running" && e.ts) return e.ts;
    }
    return job.created_at;
  }
  return job.created_at;
}

export function jobStatusLabel(status: string): string {
  const s = status.toLowerCase();
  if (s === "resuming") return "Resuming";
  if (s === "running") return "Running";
  if (s === "queued" || s === "pending") return "Queued";
  return status;
}

/** Human pipeline stage; null when it would duplicate the status badge. */
export function jobChipStep(job: JobStatus, nowMs = Date.now()): string | null {
  const status = job.status.toLowerCase();
  if (status === "queued" || status === "pending") return "Awaiting slot";

  const rows = buildPipelineNodeRows(job.status, job.progress_events ?? [], {
    createdAt: job.created_at ?? undefined,
    lastGraphStep: job.last_graph_step,
    nowMs,
  });
  const active = [...rows].reverse().find((r) => r.state === "running");
  if (active && active.id !== "queued") return active.label;

  const lastDone = [...rows].reverse().find((r) => r.state === "done");
  if (lastDone && lastDone.id !== "queued") return lastDone.label;

  return null;
}

export function jobChipTone(status: string): "running" | "queued" | "other" {
  const s = status.toLowerCase();
  if (s === "running" || s === "resuming") return "running";
  if (s === "queued" || s === "pending") return "queued";
  return "other";
}
