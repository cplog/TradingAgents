import { useEffect, useMemo, useState } from "react";
import type { JobStatus } from "../api";
import {
  buildPipelineNodeRows,
  formatPipelineElapsed,
  type PipelineNodeRow,
} from "../utils/pipelineProgress";

type Props = {
  job: JobStatus | null;
  events: { ts: string; stage: string; message: string }[];
  className?: string;
};

function stateIcon(state: PipelineNodeRow["state"]): string {
  switch (state) {
    case "done":
      return "✓";
    case "running":
      return "●";
    case "failed":
      return "✕";
    default:
      return "○";
  }
}

export function PipelineNodeProgress({ job, events, className = "" }: Props) {
  const [, tick] = useState(0);
  const jobActive =
    job?.status === "running" || job?.status === "queued" || job?.status === "resuming";

  useEffect(() => {
    if (!jobActive) return;
    const id = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [jobActive]);

  const rows = useMemo(
    () =>
      buildPipelineNodeRows(job?.status ?? "idle", events, {
        createdAt: job?.created_at,
        lastGraphStep: job?.last_graph_step,
      }),
    [job?.status, job?.created_at, job?.last_graph_step, events, tick]
  );

  if (!job || job.status === "idle") return null;

  return (
    <section
      className={`pipeline-nodes ${className}`.trim()}
      aria-label="Pipeline progress by stage"
    >
      <div className="pipeline-nodes__header">
        <span className="ui-label">Pipeline stages</span>
        {jobActive && (
          <span className="pipeline-nodes__heartbeat" role="status">
            Live · heartbeat ~45s during long LLM calls
          </span>
        )}
      </div>
      <ol className="pipeline-nodes__list">
        {rows.map((row) => (
          <li
            key={row.id}
            className={`pipeline-nodes__item pipeline-nodes__item--${row.state}`}
          >
            <span className="pipeline-nodes__icon" aria-hidden>
              {stateIcon(row.state)}
            </span>
            <div className="pipeline-nodes__body">
              <div className="pipeline-nodes__title">
                <span>{row.label}</span>
                {row.elapsedSec != null && (
                  <span className="pipeline-nodes__elapsed mono">
                    {formatPipelineElapsed(row.elapsedSec)}
                  </span>
                )}
              </div>
              {row.detail && (
                <p className="pipeline-nodes__detail">{row.detail}</p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
