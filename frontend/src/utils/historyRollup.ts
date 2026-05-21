import type { HistoryJobStatus, HistoryTableRow } from "./historyDisplay";
import { parseHistoryInstant } from "./historyDisplay";

export type TickerRollup = {
  ticker: string;
  runs: HistoryTableRow[];
  /** Most recent run by processing_at (any status). */
  latestRun: HistoryTableRow;
  /** Most recent *completed* run, used for re-run + open-latest defaults. */
  latestCompletedRun: HistoryTableRow | null;
  runCount: number;
  completedRunCount: number;
  /** First non-completed status if any run for this ticker is in flight. */
  activeStatus: HistoryJobStatus | null;
  /** ISO of most recent processing_at (any status). */
  latestProcessingAt: string | null;
};

const ACTIVE: ReadonlySet<HistoryJobStatus> = new Set([
  "running",
  "queued",
  "failed",
]);

function pickLatest(
  rows: HistoryTableRow[],
  predicate?: (r: HistoryTableRow) => boolean,
): HistoryTableRow | null {
  let best: HistoryTableRow | null = null;
  let bestMs = -Infinity;
  for (const r of rows) {
    if (predicate && !predicate(r)) continue;
    const ms = parseHistoryInstant(r.processing_at) ?? 0;
    if (ms >= bestMs) {
      best = r;
      bestMs = ms;
    }
  }
  return best;
}

/**
 * Group history rows by ticker. Rows with a missing/blank ticker are bucketed
 * under "—" so the user can still see them on the cards view.
 */
export function groupRunsByTicker(rows: HistoryTableRow[]): TickerRollup[] {
  const buckets = new Map<string, HistoryTableRow[]>();
  for (const r of rows) {
    const key = (r.ticker ?? "—").toString().trim().toUpperCase() || "—";
    const list = buckets.get(key);
    if (list) list.push(r);
    else buckets.set(key, [r]);
  }

  const out: TickerRollup[] = [];
  for (const [ticker, runs] of buckets) {
    const latestRun = pickLatest(runs)!;
    const latestCompletedRun = pickLatest(runs, (r) => r.job_status === "completed");
    const active = runs.find((r) => ACTIVE.has(r.job_status));
    out.push({
      ticker,
      runs,
      latestRun,
      latestCompletedRun,
      runCount: runs.length,
      completedRunCount: runs.filter((r) => r.job_status === "completed").length,
      activeStatus: active ? active.job_status : null,
      latestProcessingAt: latestRun.processing_at,
    });
  }

  out.sort((a, b) => {
    const am = parseHistoryInstant(a.latestProcessingAt) ?? 0;
    const bm = parseHistoryInstant(b.latestProcessingAt) ?? 0;
    return bm - am || a.ticker.localeCompare(b.ticker);
  });
  return out;
}

/** Human-readable "x days ago" / "today" relative to now (ms granularity). */
export function relativeFromNow(iso: string | null | undefined, now: number = Date.now()): string {
  const ms = parseHistoryInstant(iso);
  if (ms == null) return "—";
  const diff = now - ms;
  if (diff < 0) return "just now";
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const days = Math.floor(hr / 24);
  if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
}
