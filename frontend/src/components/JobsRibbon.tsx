import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { runsPath } from "../navigation/routes";
import { fetchConfig, type JobStatus } from "../api";
import { useJobsTracker } from "../hooks/useJobsTracker";

/**
 * Persistent analysis status bar (above main content).
 *
 * Shows every in-flight job (queued / running / resuming) in one scrollable row.
 * Completed jobs are not listed here — use History or the brief completion toast.
 * Server runs up to `max_concurrency` graph propagations in parallel (default 3);
 * additional submits queue until a slot frees.
 */

type ToastSpec = {
  id: string;
  jobId: string;
  ticker: string;
  outcome: "completed" | "failed" | "canceled";
};

function statusTone(status: string): {
  label: string;
  bg: string;
  fg: string;
  border: string;
  pulse: boolean;
} {
  const s = status.toLowerCase();
  if (s === "running" || s === "resuming") {
    return {
      label: status,
      bg: "rgba(120, 240, 168, 0.14)",
      fg: "var(--color-phosphor)",
      border: "1px solid rgba(120, 240, 168, 0.45)",
      pulse: true,
    };
  }
  if (s === "queued" || s === "pending") {
    return {
      label: status,
      bg: "var(--surface-elevated)",
      fg: "var(--color-slate-text)",
      border: "1px solid var(--color-platinum-outline)",
      pulse: false,
    };
  }
  return {
    label: status,
    bg: "var(--surface-elevated)",
    fg: "var(--color-ash-gray)",
    border: "1px solid var(--color-platinum-outline)",
    pulse: false,
  };
}

function elapsedSince(iso: string | null | undefined): string {
  if (!iso) return "";
  const ms = Date.now() - Date.parse(iso);
  if (!Number.isFinite(ms) || ms < 0) return "";
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

function jobLastStep(job: JobStatus): string | null {
  const events = job.progress_events ?? [];
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const stage = events[i]?.stage;
    if (stage && stage.trim()) return stage.trim();
  }
  return null;
}

function countByStatus(jobs: JobStatus[], statuses: string[]): number {
  const want = new Set(statuses.map((s) => s.toLowerCase()));
  return jobs.filter((j) => want.has(j.status.toLowerCase())).length;
}

function buildStatusSummary(active: JobStatus[], maxConcurrency: number | null): string {
  if (active.length === 0) return "No analyses in progress";
  const running = countByStatus(active, ["running", "resuming"]);
  const queued = countByStatus(active, ["queued", "pending"]);
  const parts: string[] = [];
  if (running > 0) parts.push(`${running} running`);
  if (queued > 0) parts.push(`${queued} queued`);
  const head = parts.length ? parts.join(" · ") : `${active.length} active`;
  if (maxConcurrency != null && maxConcurrency > 0) {
    return `${head} · up to ${maxConcurrency} in parallel`;
  }
  return head;
}

export function JobsRibbon() {
  const navigate = useNavigate();
  const { active, recentlyCompleted, justCompletedIds, error } = useJobsTracker();
  const [maxConcurrency, setMaxConcurrency] = useState<number | null>(null);
  const [toasts, setToasts] = useState<ToastSpec[]>([]);
  const [, setNowTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void fetchConfig()
      .then((cfg) => {
        if (cancelled) return;
        const raw = cfg.max_concurrency;
        if (typeof raw === "number" && Number.isFinite(raw) && raw > 0) {
          setMaxConcurrency(Math.floor(raw));
        }
      })
      .catch(() => {
        if (!cancelled) setMaxConcurrency(3);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (active.length === 0) return;
    const id = setInterval(() => setNowTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [active.length]);

  const toastTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  useEffect(() => {
    if (justCompletedIds.length === 0) return;
    const lookup = new Map<string, JobStatus>();
    for (const j of recentlyCompleted) lookup.set(j.job_id, j);

    setToasts((prev) => {
      const seen = new Set(prev.map((t) => t.id));
      const next = [...prev];
      for (const jobId of justCompletedIds) {
        if (seen.has(jobId)) continue;
        const j = lookup.get(jobId);
        if (!j) continue;
        const outcome: ToastSpec["outcome"] =
          j.status.toLowerCase() === "completed"
            ? "completed"
            : j.status.toLowerCase() === "failed"
              ? "failed"
              : "canceled";
        next.push({
          id: jobId,
          jobId,
          ticker: (j.ticker ?? "—").toUpperCase(),
          outcome,
        });
        const t = setTimeout(() => {
          setToasts((curr) => curr.filter((x) => x.id !== jobId));
          toastTimers.current.delete(jobId);
        }, 6000);
        toastTimers.current.set(jobId, t);
      }
      return next;
    });
  }, [justCompletedIds, recentlyCompleted]);

  useEffect(() => {
    const timers = toastTimers.current;
    return () => {
      timers.forEach((t) => clearTimeout(t));
      timers.clear();
    };
  }, []);

  const statusSummary = useMemo(
    () => buildStatusSummary(active, maxConcurrency),
    [active, maxConcurrency],
  );

  if (active.length === 0 && toasts.length === 0 && !error) return null;

  return (
    <div className="analysis-status-bar" role="region" aria-label="Analysis status">
      <div className="analysis-status-bar__head">
        <span className="analysis-status-bar__title">Analysis</span>
        <span className="analysis-status-bar__summary">{statusSummary}</span>
      </div>

      {active.length > 0 && (
        <div className="analysis-status-bar__track" role="list" aria-label="In-progress tickers">
          {active.map((job) => {
            const tone = statusTone(job.status);
            const ticker = (job.ticker ?? "—").toUpperCase();
            const step = jobLastStep(job);
            const elapsed = elapsedSince(job.created_at);
            return (
              <button
                key={job.job_id}
                type="button"
                role="listitem"
                className={`analysis-status-bar__item${tone.pulse ? " analysis-status-bar__item--pulse" : ""}`}
                style={{
                  background: tone.bg,
                  color: tone.fg,
                  border: tone.border,
                }}
                onClick={() => navigate(runsPath(job.job_id))}
                title={
                  `${ticker} · ${tone.label}${step ? ` · ${step}` : ""}` +
                  (elapsed ? ` · ${elapsed}` : "") +
                  ` · job ${job.job_id}`
                }
              >
                <span className="analysis-status-bar__item-dot" aria-hidden />
                <span className="analysis-status-bar__item-ticker">{ticker}</span>
                <span className="analysis-status-bar__item-status">{tone.label}</span>
                {step ? <span className="analysis-status-bar__item-step">{step}</span> : null}
                {elapsed ? <span className="analysis-status-bar__item-elapsed">{elapsed}</span> : null}
              </button>
            );
          })}
        </div>
      )}

      {toasts.length > 0 && (
        <div className="analysis-status-bar__toasts" aria-live="polite">
          {toasts.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`analysis-status-bar__toast analysis-status-bar__toast--${t.outcome}`}
              onClick={() =>
                navigate(
                  t.outcome === "completed"
                    ? `${runsPath(t.jobId)}?tab=reports`
                    : runsPath(t.jobId),
                )
              }
            >
              <strong>{t.ticker}</strong>{" "}
              {t.outcome === "completed" ? "done" : t.outcome === "failed" ? "failed" : "stopped"}
              <span className="analysis-status-bar__toast-action">
                {t.outcome === "completed" ? "View →" : "Open →"}
              </span>
            </button>
          ))}
        </div>
      )}

      {error && active.length === 0 && (
        <div className="analysis-status-bar__error" role="alert">
          Status offline: {error}
        </div>
      )}
    </div>
  );
}
