import type { HistoryRunRef, JobStatus } from "../api";

/** Display timestamps in Hong Kong local time. */
export const HISTORY_TIMEZONE = "Asia/Hong_Kong";

export type HistoryJobStatus =
  | "completed"
  | "queued"
  | "running"
  | "failed"
  | "cancelled"
  | "unknown";

export type HistorySortKey =
  | "processing_desc"
  | "processing_asc"
  | "ticker_asc"
  | "ticker_desc"
  | "trade_date_desc"
  | "trade_date_asc"
  | "rating_desc"
  | "rating_asc"
  | "confidence_desc"
  | "confidence_asc"
  | "status_asc"
  | "status_desc";

export type HistoryTableRow = HistoryRunRef & {
  job_status: HistoryJobStatus;
  /** ISO timestamp used for default sort (completed_at or job created_at). */
  processing_at: string | null;
  is_live_job: boolean;
  resumable?: boolean;
};

const RATING_RANK: Record<string, number> = {
  Buy: 5,
  Overweight: 4,
  Hold: 3,
  Underweight: 2,
  Sell: 1,
};

const STATUS_RANK: Record<HistoryJobStatus, number> = {
  running: 6,
  queued: 5,
  failed: 4,
  cancelled: 3,
  completed: 2,
  unknown: 1,
};

export function parseHistoryInstant(iso: string | null | undefined): number | null {
  if (!iso || !String(iso).trim()) return null;
  const raw = String(iso).trim();
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(raw) ? raw : `${raw}Z`;
  const ms = Date.parse(normalized);
  return Number.isFinite(ms) ? ms : null;
}

export function formatHistoryTimestamp(iso: string | null | undefined): string {
  const ms = parseHistoryInstant(iso);
  if (ms == null) return "—";
  return new Intl.DateTimeFormat("en-HK", {
    timeZone: HISTORY_TIMEZONE,
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(ms));
}

export function formatHistoryTimestampWithZone(iso: string | null | undefined): string {
  const text = formatHistoryTimestamp(iso);
  return text === "—" ? text : `${text} HKT`;
}

function rowFromHistory(run: HistoryRunRef): HistoryTableRow {
  return {
    ...run,
    provenance: run.provenance ?? null,
    job_status: "completed",
    processing_at: run.completed_at ?? run.created_at ?? null,
    is_live_job: false,
  };
}

function rowFromJob(job: JobStatus): HistoryTableRow {
  const status = (job.status ?? "unknown") as HistoryJobStatus;
  const completedAt = job.result?.completed_at ?? null;
  return {
    run_id: job.job_id,
    job_id: job.job_id,
    ticker: job.ticker ?? null,
    date: job.date ?? null,
    rating:
      job.result?.rating ??
      (status === "failed" ? null : status === "running" || status === "queued" ? "…" : null),
    confidence: job.result?.confidence ?? null,
    completed_at: completedAt,
    created_at: job.created_at,
    batch_id: job.batch_id ?? null,
    job_status: status,
    processing_at: completedAt ?? job.created_at ?? null,
    is_live_job: status !== "completed",
    resumable: job.resumable,
    provenance: job.provenance ?? null,
  };
}

function matchesFilters(
  row: HistoryTableRow,
  filters: { ticker?: string; dateFrom?: string; dateTo?: string },
): boolean {
  const ticker = filters.ticker?.trim().toUpperCase();
  if (ticker && String(row.ticker ?? "").toUpperCase() !== ticker) {
    return false;
  }
  const d = String(row.date ?? "");
  if (filters.dateFrom && d && d < filters.dateFrom) return false;
  if (filters.dateTo && d && d > filters.dateTo) return false;
  return true;
}

/** Merge persisted history with live job store rows (in-progress + recent failures). */
export function mergeHistoryAndJobs(
  history: HistoryRunRef[],
  jobs: JobStatus[],
  filters: { ticker?: string; dateFrom?: string; dateTo?: string } = {},
): HistoryTableRow[] {
  const byId = new Map<string, HistoryTableRow>();

  for (const run of history) {
    const row = rowFromHistory(run);
    if (matchesFilters(row, filters)) {
      byId.set(row.run_id, row);
    }
  }

  for (const job of jobs) {
    const row = rowFromJob(job);
    if (!matchesFilters(row, filters)) continue;
    const existing = byId.get(job.job_id);
    if (job.status === "completed") {
      if (!existing) {
        byId.set(job.job_id, { ...row, is_live_job: false });
      }
      continue;
    }
    byId.set(job.job_id, row);
  }

  return Array.from(byId.values());
}

function ratingRank(rating: string | null | undefined): number {
  if (!rating) return -1;
  return RATING_RANK[rating] ?? 0;
}

function cmpString(a: string | null | undefined, b: string | null | undefined): number {
  return String(a ?? "").localeCompare(String(b ?? ""), undefined, { sensitivity: "base" });
}

export function sortHistoryRows(rows: HistoryTableRow[], sortKey: HistorySortKey): HistoryTableRow[] {
  const out = [...rows];
  out.sort((a, b) => {
    switch (sortKey) {
      case "processing_desc": {
        const da = parseHistoryInstant(a.processing_at) ?? 0;
        const db = parseHistoryInstant(b.processing_at) ?? 0;
        return db - da || cmpString(a.run_id, b.run_id);
      }
      case "processing_asc": {
        const da = parseHistoryInstant(a.processing_at) ?? 0;
        const db = parseHistoryInstant(b.processing_at) ?? 0;
        return da - db || cmpString(a.run_id, b.run_id);
      }
      case "ticker_asc":
        return cmpString(a.ticker, b.ticker) || cmpString(b.date, a.date);
      case "ticker_desc":
        return cmpString(b.ticker, a.ticker) || cmpString(b.date, a.date);
      case "trade_date_desc":
        return cmpString(b.date, a.date) || cmpString(b.ticker, a.ticker);
      case "trade_date_asc":
        return cmpString(a.date, b.date) || cmpString(a.ticker, b.ticker);
      case "rating_desc":
        return ratingRank(b.rating) - ratingRank(a.rating) || cmpString(b.date, a.date);
      case "rating_asc":
        return ratingRank(a.rating) - ratingRank(b.rating) || cmpString(b.date, a.date);
      case "confidence_desc":
        return (b.confidence ?? -1) - (a.confidence ?? -1);
      case "confidence_asc":
        return (a.confidence ?? -1) - (b.confidence ?? -1);
      case "status_desc":
        return STATUS_RANK[b.job_status] - STATUS_RANK[a.job_status];
      case "status_asc":
        return STATUS_RANK[a.job_status] - STATUS_RANK[b.job_status];
      default:
        return 0;
    }
  });
  return out;
}

export function statusLabel(status: HistoryJobStatus): string {
  switch (status) {
    case "queued":
      return "Queued";
    case "running":
      return "Running";
    case "failed":
      return "Failed";
    case "cancelled":
      return "Cancelled";
    case "completed":
      return "Completed";
    default:
      return "Unknown";
  }
}

export function hasActiveHistoryRows(rows: HistoryTableRow[]): boolean {
  return rows.some((r) => r.job_status === "queued" || r.job_status === "running");
}
