import { useEffect, useRef, useState } from "react";
import { fetchJobs, type JobStatus } from "../api";
import { sortActiveJobs } from "../utils/activeJobsDisplay";

/**
 * Lightweight cross-page jobs tracker for the persistent jobs ribbon.
 *
 * Polls `/jobs?limit=20` on an interval (2s while anything is in-flight,
 * 15s when everything is quiet) and reports:
 *   - active: queued/running/resuming jobs
 *   - recentlyCompleted: jobs that finished within the past hour
 *   - justCompletedIds: jobs that transitioned to a terminal state on
 *     *this* tick, so the consumer can fire a one-shot toast.
 *
 * Polling (rather than wiring SSE here) keeps this hook trivial and avoids
 * holding ~N open EventSource connections from the layout shell. The real
 * /dashboard?job=ID page still uses SSE for fine-grained per-event updates.
 */

const TERMINAL: ReadonlySet<string> = new Set([
  "completed",
  "failed",
  "canceled",
  "cancelled",
]);

const RECENT_WINDOW_MS = 60 * 60 * 1000;

function isTerminal(status: string): boolean {
  return TERMINAL.has(status.toLowerCase());
}

function parseTs(s: string | undefined | null): number {
  if (!s) return 0;
  const t = Date.parse(s);
  return Number.isFinite(t) ? t : 0;
}

function jobEndedAtMs(job: JobStatus): number {
  if (!isTerminal(job.status)) return 0;
  const events = job.progress_events ?? [];
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const t = parseTs(events[i]?.ts);
    if (t) return t;
  }
  return parseTs(job.created_at);
}

export type JobsTracker = {
  active: JobStatus[];
  recentlyCompleted: JobStatus[];
  /** Job ids that became terminal on the most recent fetch (one-shot). */
  justCompletedIds: string[];
  loading: boolean;
  error: string | null;
  /** Manual refetch — useful right after submitting a job. */
  refresh: () => void;
};

export function useJobsTracker(): JobsTracker {
  const [active, setActive] = useState<JobStatus[]>([]);
  const [recentlyCompleted, setRecentlyCompleted] = useState<JobStatus[]>([]);
  const [justCompletedIds, setJustCompletedIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pulse, setPulse] = useState(0);

  const knownStatuses = useRef<Map<string, string>>(new Map());

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function tick(): Promise<void> {
      try {
        const jobs = await fetchJobs(20);
        if (cancelled) return;
        const now = Date.now();
        const nextActive: JobStatus[] = [];
        const nextRecent: JobStatus[] = [];
        const newlyCompleted: string[] = [];

        for (const job of jobs) {
          const prevStatus = knownStatuses.current.get(job.job_id);
          const status = job.status.toLowerCase();
          if (isTerminal(status)) {
            const ended = jobEndedAtMs(job);
            if (now - ended <= RECENT_WINDOW_MS) {
              nextRecent.push(job);
            }
            if (prevStatus && !isTerminal(prevStatus)) {
              newlyCompleted.push(job.job_id);
            }
          } else {
            nextActive.push(job);
          }
          knownStatuses.current.set(job.job_id, status);
        }

        const sortedActive = sortActiveJobs(nextActive);
        nextRecent.sort((a, b) => jobEndedAtMs(b) - jobEndedAtMs(a));

        if (cancelled) return;
        setActive(sortedActive);
        setRecentlyCompleted(nextRecent);
        setJustCompletedIds(newlyCompleted);
        setError(null);
        const wait = nextActive.length > 0 ? 2000 : 15000;
        timer = setTimeout(() => void tick(), wait);
      } catch (e: unknown) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        timer = setTimeout(() => void tick(), 15000);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // `pulse` increments cause the effect to tear down + restart → immediate refetch.
  }, [pulse]);

  function refresh(): void {
    setPulse((n) => n + 1);
  }

  return { active, recentlyCompleted, justCompletedIds, loading, error, refresh };
}
