import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { runsPath } from "../navigation/routes";
import { fetchConfig, type JobStatus } from "../api";
import { useJobsTracker } from "../hooks/useJobsTracker";
import {
  formatElapsedSince,
  jobChipStep,
  jobChipTone,
  jobElapsedAnchorIso,
  jobStatusLabel,
  partitionActiveJobs,
} from "../utils/activeJobsDisplay";

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

type JobChipProps = {
  job: JobStatus;
  index: number;
  nowMs: number;
  onOpen: (jobId: string) => void;
};

function JobChip({ job, index, nowMs, onOpen }: JobChipProps) {
  const tone = jobChipTone(job.status);
  const ticker = (job.ticker ?? "—").toUpperCase();
  const statusText = jobStatusLabel(job.status);
  const step = jobChipStep(job, nowMs);
  const elapsed = formatElapsedSince(jobElapsedAnchorIso(job), nowMs);
  const showStep = step && step.toLowerCase() !== statusText.toLowerCase();

  return (
    <button
      key={job.job_id}
      type="button"
      role="listitem"
      className={`analysis-status-bar__item analysis-status-bar__item--${tone}`}
      data-status={tone}
      style={{ "--chip-index": index } as React.CSSProperties}
      onClick={() => onOpen(job.job_id)}
      title={
        `${ticker} · ${statusText}${showStep && step ? ` · ${step}` : ""}` +
        (elapsed ? ` · ${elapsed}` : "") +
        ` · job ${job.job_id}`
      }
    >
      <span className="analysis-status-bar__item-dot" aria-hidden />
      <span className="analysis-status-bar__item-ticker">{ticker}</span>
      <span className="analysis-status-bar__item-status">{statusText}</span>
      {showStep ? <span className="analysis-status-bar__item-step">{step}</span> : null}
      {elapsed ? <span className="analysis-status-bar__item-elapsed">{elapsed}</span> : null}
    </button>
  );
}

export function JobsRibbon() {
  const navigate = useNavigate();
  const { active, recentlyCompleted, justCompletedIds, error } = useJobsTracker();
  const [maxConcurrency, setMaxConcurrency] = useState<number | null>(null);
  const [toasts, setToasts] = useState<ToastSpec[]>([]);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const trackRef = useRef<HTMLDivElement>(null);

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
    const id = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active.length]);

  const { running, queued } = useMemo(() => partitionActiveJobs(active), [active]);
  const runningCount = running.length;
  const slotCount = maxConcurrency ?? 3;

  useEffect(() => {
    const el = trackRef.current;
    if (!el || runningCount === 0) return;
    if (typeof el.scrollTo === "function") {
      el.scrollTo({ left: 0, behavior: "smooth" });
    } else {
      el.scrollLeft = 0;
    }
  }, [runningCount, running[0]?.job_id]);

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

  const openJob = (jobId: string) => navigate(runsPath(jobId));

  let chipIndex = 0;

  if (active.length === 0 && toasts.length === 0 && !error) return null;

  return (
    <div className="analysis-status-bar" role="region" aria-label="Analysis status">
      <div className="analysis-status-bar__head">
        <span className="analysis-status-bar__title">Analysis</span>
        {active.length > 0 && slotCount > 0 && (
          <div
            className="analysis-status-bar__slots"
            aria-label={`${runningCount} of ${slotCount} parallel slots in use`}
          >
            {Array.from({ length: slotCount }, (_, i) => (
              <span
                key={i}
                className={`analysis-status-bar__slot${i < runningCount ? " analysis-status-bar__slot--live" : ""}`}
                aria-hidden
              />
            ))}
          </div>
        )}
        <span className="analysis-status-bar__summary">{statusSummary}</span>
      </div>

      {active.length > 0 && (
        <div
          ref={trackRef}
          className="analysis-status-bar__track"
          role="list"
          aria-label="In-progress tickers"
        >
          {running.length > 0 && (
            <div className="analysis-status-bar__group" role="presentation">
              <span className="analysis-status-bar__group-label">Running</span>
              <div className="analysis-status-bar__group-chips" role="list">
                {running.map((job) => {
                  const idx = chipIndex++;
                  return (
                    <JobChip
                      key={job.job_id}
                      job={job}
                      index={idx}
                      nowMs={nowMs}
                      onOpen={openJob}
                    />
                  );
                })}
              </div>
            </div>
          )}
          {running.length > 0 && queued.length > 0 && (
            <span className="analysis-status-bar__divider" aria-hidden />
          )}
          {queued.length > 0 && (
            <div className="analysis-status-bar__group" role="presentation">
              <span className="analysis-status-bar__group-label">Queued</span>
              <div className="analysis-status-bar__group-chips" role="list">
                {queued.map((job) => {
                  const idx = chipIndex++;
                  return (
                    <JobChip
                      key={job.job_id}
                      job={job}
                      index={idx}
                      nowMs={nowMs}
                      onOpen={openJob}
                    />
                  );
                })}
              </div>
            </div>
          )}
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
