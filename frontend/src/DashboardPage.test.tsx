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
});
