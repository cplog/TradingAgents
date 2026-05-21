import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { JobsRibbon } from "./JobsRibbon";
import type { JobStatus } from "../api";
import * as api from "../api";

function makeJob(overrides: Partial<JobStatus> & { job_id: string }): JobStatus {
  return {
    job_id: overrides.job_id,
    status: overrides.status ?? "running",
    created_at: overrides.created_at ?? "2026-05-20T00:00:00Z",
    ticker: overrides.ticker ?? "AAPL",
    date: overrides.date ?? null,
    result: overrides.result ?? null,
    error: overrides.error ?? null,
    progress_events: overrides.progress_events ?? [],
    batch_id: overrides.batch_id ?? null,
    resumable: overrides.resumable ?? false,
    last_graph_step: overrides.last_graph_step ?? null,
    checkpoint_thread_id: overrides.checkpoint_thread_id ?? null,
  };
}

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="loc">{loc.pathname}</div>;
}

describe("JobsRibbon", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders a chip for each in-flight job and routes on click", async () => {
    vi.spyOn(api, "fetchJobs").mockResolvedValue([
      makeJob({ job_id: "j-1", ticker: "nvda", status: "running" }),
      makeJob({ job_id: "j-2", ticker: "msft", status: "queued" }),
    ]);

    render(
      <MemoryRouter initialEntries={["/start"]}>
        <Routes>
          <Route path="*" element={<><JobsRibbon /><LocationProbe /></>} />
        </Routes>
      </MemoryRouter>,
    );

    // Drain the pending fetch promise.
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText("NVDA")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getAllByText(/running|queued/i).length).toBeGreaterThanOrEqual(2);

    fireEvent.click(screen.getByText("NVDA").closest("button")!);
    expect(screen.getByTestId("loc").textContent).toBe("/runs/j-1");
  });

  it("hides itself when there are no active jobs or recent completions", async () => {
    vi.spyOn(api, "fetchJobs").mockResolvedValue([]);

    const { container } = render(
      <MemoryRouter>
        <JobsRibbon />
      </MemoryRouter>,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(container.querySelector(".analysis-status-bar")).toBeNull();
  });

  it("fires a toast when a job transitions from running to completed", async () => {
    const spy = vi.spyOn(api, "fetchJobs");
    spy.mockResolvedValueOnce([
      makeJob({ job_id: "j-3", ticker: "tsla", status: "running" }),
    ]);

    render(
      <MemoryRouter>
        <JobsRibbon />
      </MemoryRouter>,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText("TSLA")).toBeInTheDocument();

    // Next tick: same job now reports completed.
    spy.mockResolvedValueOnce([
      makeJob({
        job_id: "j-3",
        ticker: "tsla",
        status: "completed",
        progress_events: [
          { ts: new Date().toISOString(), stage: "done", message: "ok" },
        ],
      }),
    ]);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    // Allow any pending state updates from the re-fetch closure to settle.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });

    expect(screen.getByText("done")).toBeInTheDocument();
    expect(screen.getByText("View →")).toBeInTheDocument();
  });
});
