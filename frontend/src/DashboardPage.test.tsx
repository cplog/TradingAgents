import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";
import { DashboardPage } from "./pages/DashboardPage";

describe("DashboardPage", () => {
  let storageBacking: Record<string, string>;

  beforeEach(() => {
    vi.restoreAllMocks();
    storageBacking = {};
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: vi.fn((key: string) => storageBacking[key] ?? null),
        setItem: vi.fn((key: string, value: string) => {
          storageBacking[key] = value;
        }),
        removeItem: vi.fn((key: string) => {
          delete storageBacking[key];
        }),
      },
    });
    class MockEventSource {
      onmessage: ((event: MessageEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      close() {
        /* no-op */
      }
    }
    (globalThis as { EventSource?: unknown }).EventSource = MockEventSource as unknown;
  });

  it("clears stale completed saved job instead of showing old report", async () => {
    window.localStorage.setItem("ta:lastJobId", "old123");
    const removeSpy = vi.spyOn(window.localStorage, "removeItem");

    vi.spyOn(api, "fetchConfig").mockResolvedValue({});
    vi.spyOn(api, "getJob").mockResolvedValue({
      job_id: "old123",
      status: "completed",
      created_at: "2026-05-14T12:00:00Z",
      ticker: "AAPL",
      date: "2026-05-14",
      result: {
        ticker: "AAPL",
        date: "2026-05-14",
        rating: "Buy",
        reports: {
          portfolio_decision: "OLD REPORT CONTENT",
        },
        completed_at: "2026-05-14T12:05:00Z",
      },
      error: null,
      progress_events: [],
      batch_id: null,
    });

    const el = document.createElement("div");
    document.body.appendChild(el);

    await act(async () => {
      createRoot(el).render(
        <StrictMode>
          <MemoryRouter initialEntries={["/dashboard"]}>
            <DashboardPage />
          </MemoryRouter>
        </StrictMode>
      );
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(removeSpy).toHaveBeenCalledWith("ta:lastJobId");
    expect(storageBacking["ta:lastJobId"]).toBeUndefined();
    expect(el.textContent).toContain("Previous job is already finished.");
    expect(el.textContent).not.toContain("OLD REPORT CONTENT");
  });

  it("keeps a completed job visible when opened via ?job= deep link", async () => {
    vi.spyOn(api, "fetchConfig").mockResolvedValue({});
    vi.spyOn(api, "getJob").mockResolvedValue({
      job_id: "deeplink99",
      status: "completed",
      created_at: "2026-05-14T12:00:00Z",
      ticker: "MSFT",
      date: "2026-05-14",
      result: {
        ticker: "MSFT",
        date: "2026-05-14",
        rating: "Hold",
        reports: {
          portfolio_decision: "## Decision\nHold while reviewing.",
        },
        completed_at: "2026-05-14T12:05:00Z",
      },
      error: null,
      progress_events: [],
      batch_id: null,
    });

    const el = document.createElement("div");
    document.body.appendChild(el);

    await act(async () => {
      createRoot(el).render(
        <StrictMode>
          <MemoryRouter initialEntries={["/dashboard?job=deeplink99"]}>
            <DashboardPage />
          </MemoryRouter>
        </StrictMode>,
      );
    });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(api.getJob).toHaveBeenCalledWith("deeplink99");
    expect(el.textContent).toContain("deeplink99");
    expect(el.textContent).toContain("completed");
    expect(el.textContent).toContain("/runs/deeplink99");
    expect(el.textContent).not.toContain("Previous job is already finished.");
  });

  it("loads persisted history when deep-linked job is missing from worker memory", async () => {
    vi.spyOn(api, "fetchConfig").mockResolvedValue({});
    vi.spyOn(api, "fetchHealth").mockResolvedValue({
      ok: true,
      llm_provider: "openai",
      api_key_configured: true,
      state_store: "local_file",
      cloudflare_kv_configured: false,
      data_cache_dir: "/tmp",
      results_dir: "/tmp",
      yfinance_reachable: true,
      supported_analyst_ids: ["market", "social", "news", "fundamentals"],
    });
    vi.spyOn(api, "getJob").mockRejectedValue(new Error('404: {"detail":"Job not found"}'));
    vi.spyOn(api, "fetchHistoryRun").mockResolvedValue({
      run_id: "hist1",
      job_id: "hist1",
      ticker: "AAPL",
      date: "2026-05-19",
      rating: "Buy",
      confidence: 0.92,
      reports: {
        market: "Market analyst body",
        portfolio_decision: "PM decision",
      },
      config_snapshot: {},
      completed_at: "2026-05-19T12:00:00Z",
    });

    const el = document.createElement("div");
    document.body.appendChild(el);

    await act(async () => {
      createRoot(el).render(
        <StrictMode>
          <MemoryRouter initialEntries={["/dashboard?job=hist1&tab=reports"]}>
            <DashboardPage />
          </MemoryRouter>
        </StrictMode>,
      );
    });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(api.fetchHistoryRun).toHaveBeenCalledWith("hist1");
    expect(el.textContent).toContain("Market analyst body");
    expect(el.textContent).toContain("Agent reports");
    expect(el.textContent).not.toContain("Job not found");
  });
});
