import { describe, expect, it } from "vitest";
import type { JobStatus } from "../api";
import {
  formatElapsedSince,
  jobChipStep,
  jobElapsedAnchorIso,
  partitionActiveJobs,
  sortActiveJobs,
} from "./activeJobsDisplay";

function job(
  id: string,
  status: string,
  createdAt: string,
  events: JobStatus["progress_events"] = [],
): JobStatus {
  return {
    job_id: id,
    status,
    created_at: createdAt,
    ticker: id,
    date: null,
    result: null,
    error: null,
    progress_events: events,
    batch_id: null,
    resumable: false,
    last_graph_step: null,
    checkpoint_thread_id: null,
  };
}

describe("sortActiveJobs", () => {
  it("orders running before queued, FIFO within each group", () => {
    const input = [
      job("q-new", "queued", "2026-05-20T12:00:00Z"),
      job("r-old", "running", "2026-05-20T10:00:00Z"),
      job("q-old", "queued", "2026-05-20T11:00:00Z"),
      job("r-new", "running", "2026-05-20T11:30:00Z"),
    ];
    const ids = sortActiveJobs(input).map((j) => j.job_id);
    expect(ids).toEqual(["r-old", "r-new", "q-old", "q-new"]);
  });
});

describe("partitionActiveJobs", () => {
  it("splits running and queued in display order", () => {
    const { running, queued } = partitionActiveJobs([
      job("q1", "queued", "2026-05-20T12:00:00Z"),
      job("r1", "running", "2026-05-20T10:00:00Z"),
    ]);
    expect(running.map((j) => j.job_id)).toEqual(["r1"]);
    expect(queued.map((j) => j.job_id)).toEqual(["q1"]);
  });
});

describe("formatElapsedSince", () => {
  it("uses hours for long waits", () => {
    const now = Date.parse("2026-05-20T12:00:00Z");
    const text = formatElapsedSince("2026-05-20T03:00:00Z", now);
    expect(text).toBe("9h");
  });
});

describe("jobElapsedAnchorIso", () => {
  it("uses created_at for queued jobs", () => {
    const j = job("q", "queued", "2026-05-20T03:00:00Z");
    expect(jobElapsedAnchorIso(j)).toBe("2026-05-20T03:00:00Z");
  });

  it("uses first running after latest queued, not created_at", () => {
    const j = job("r", "running", "2026-05-20T03:00:00Z", [
      { ts: "2026-05-20T03:00:00Z", stage: "queued", message: "Job queued" },
      { ts: "2026-05-20T11:08:00Z", stage: "running", message: "Starting pipeline" },
    ]);
    expect(jobElapsedAnchorIso(j)).toBe("2026-05-20T11:08:00Z");
    const now = Date.parse("2026-05-20T11:10:00Z");
    expect(formatElapsedSince(jobElapsedAnchorIso(j), now)).toBe("2m 00s");
  });

  it("after resume, anchors from running events after the resume queued event", () => {
    const j = job("r", "running", "2026-05-20T03:00:00Z", [
      { ts: "2026-05-20T03:00:00Z", stage: "queued", message: "Job queued" },
      { ts: "2026-05-20T04:00:00Z", stage: "running", message: "Starting" },
      { ts: "2026-05-20T11:00:00Z", stage: "queued", message: "Resuming from checkpoint" },
      { ts: "2026-05-20T11:05:00Z", stage: "running", message: "Resuming pipeline" },
    ]);
    expect(jobElapsedAnchorIso(j)).toBe("2026-05-20T11:05:00Z");
  });
});

describe("jobChipStep", () => {
  it("returns awaiting slot for queued jobs", () => {
    expect(jobChipStep(job("x", "queued", "2026-05-20T10:00:00Z"))).toBe("Awaiting slot");
  });

  it("returns pipeline label for running jobs with events", () => {
    const step = jobChipStep(
      job("x", "running", "2026-05-20T10:00:00Z", [
        { ts: "2026-05-20T10:00:00Z", stage: "queued", message: "Job queued" },
        { ts: "2026-05-20T10:01:00Z", stage: "running", message: "Still in LangGraph (~60s elapsed)" },
      ]),
    );
    expect(step).toBe("Research & risk debate");
  });
});
