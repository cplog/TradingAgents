import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";
import { JobsTrackerProvider } from "./contexts/JobsTrackerContext";
import { HistoryPage } from "./pages/HistoryPage";

function renderHistoryPage(el: HTMLElement, initialEntries = ["/history"]) {
  return createRoot(el).render(
    <StrictMode>
      <MemoryRouter initialEntries={initialEntries}>
        <JobsTrackerProvider>
          <HistoryPage />
        </JobsTrackerProvider>
      </MemoryRouter>
    </StrictMode>,
  );
}

describe("HistoryPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "fetchJobs").mockResolvedValue([]);
  });

  // Default view is table.
  async function switchToTable(el: HTMLElement) {
    // no-op: table is the only view mode
  }

  it("lists runs and renders compare section", async () => {
    vi.spyOn(api, "fetchHistoryRuns").mockResolvedValue([
      {
        run_id: "a1",
        ticker: "AAPL",
        date: "2026-05-01",
        rating: "Buy",
        confidence: 0.92,
        completed_at: "2026-05-01T00:00:00Z",
      },
      {
        run_id: "b2",
        ticker: "MSFT",
        date: "2026-05-02",
        rating: "Hold",
        confidence: 0.55,
        completed_at: "2026-05-02T00:00:00Z",
      },
    ]);

    const el = document.createElement("div");
    document.body.appendChild(el);

    await act(async () => {
      renderHistoryPage(el);
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(el.innerHTML).toContain("Runs");
    expect(el.innerHTML).toContain("a1");
    expect(el.innerHTML).toContain("b2");
  });

  it("loads compare on button click", async () => {
    vi.spyOn(api, "fetchHistoryRuns").mockResolvedValue([
      {
        run_id: "r1",
        ticker: "AAPL",
        date: "2026-05-01",
        rating: "Buy",
      },
      {
        run_id: "r2",
        ticker: "MSFT",
        date: "2026-05-02",
        rating: "Hold",
      },
    ]);

    vi.spyOn(api, "postHistoryCompare").mockResolvedValue({
      a: {
        run_id: "r1",
        ticker: "AAPL",
        date: "2026-05-01",
        rating: "Buy",
        confidence: 0.9,
        completed_at: "",
        created_at: "",
        config_snapshot: {},
        reports: { portfolio_decision: "## Buy" },
        excerpt_portfolio_decision: "## Buy",
        excerpt_trader_plan: "Plan A",
      },
      b: {
        run_id: "r2",
        ticker: "MSFT",
        date: "2026-05-02",
        rating: "Hold",
        confidence: 0.55,
        completed_at: "",
        created_at: "",
        config_snapshot: {},
        reports: { portfolio_decision: "## Hold" },
        excerpt_portfolio_decision: "## Hold",
        excerpt_trader_plan: "Plan B",
      },
    });

    const el = document.createElement("div");
    document.body.appendChild(el);

    await act(async () => {
      renderHistoryPage(el);
    });

    await act(async () => {
      await Promise.resolve();
    });

    const compareSelectA = el.querySelector('select[aria-label="Compare run A"]') as HTMLSelectElement;
    const compareSelectB = el.querySelector('select[aria-label="Compare run B"]') as HTMLSelectElement;
    expect(compareSelectA).toBeTruthy();
    expect(compareSelectB).toBeTruthy();
    await act(async () => {
      compareSelectA.value = "r1";
      compareSelectA.dispatchEvent(new Event("change", { bubbles: true }));
      compareSelectB.value = "r2";
      compareSelectB.dispatchEvent(new Event("change", { bubbles: true }));
    });

    const btn = [...el.querySelectorAll("button")].find((b) => b.textContent === "Compare");
    expect(btn).toBeTruthy();

    await act(async () => {
      (btn as HTMLButtonElement).click();
      await Promise.resolve();
    });

    expect(api.postHistoryCompare).toHaveBeenCalledWith("r1", "r2");
    expect(el.innerHTML).toContain("AAPL vs MSFT");
  });

  it("deletes a run from the table", async () => {
    vi.spyOn(api, "fetchHistoryRuns").mockResolvedValue([
      {
        run_id: "r1",
        ticker: "AAPL",
        date: "2026-05-01",
        rating: "Buy",
      },
      {
        run_id: "r2",
        ticker: "MSFT",
        date: "2026-05-02",
        rating: "Hold",
      },
    ]);
    vi.spyOn(api, "deleteHistoryRun").mockResolvedValue({ deleted: true, run_id: "r1" });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    const el = document.createElement("div");
    document.body.appendChild(el);

    await act(async () => {
      renderHistoryPage(el);
    });

    await act(async () => {
      await Promise.resolve();
    });

    await switchToTable(el);

    const deleteBtn = [...el.querySelectorAll("button")].find(
      (b) => b.textContent === "Del" || b.textContent === "Delete",
    );
    expect(deleteBtn).toBeTruthy();

    await act(async () => {
      (deleteBtn as HTMLButtonElement).click();
      await Promise.resolve();
    });

    expect(api.deleteHistoryRun).toHaveBeenCalledWith("r1");
    expect(el.querySelector('a[href="/runs/r1"]')).toBeFalsy();
  });

  it("bulk deletes selected runs", async () => {
    vi.spyOn(api, "fetchHistoryRuns").mockResolvedValue([
      { run_id: "r1", ticker: "AAPL", date: "2026-05-01", rating: "Buy" },
      { run_id: "r2", ticker: "MSFT", date: "2026-05-02", rating: "Hold" },
    ]);
    vi.spyOn(api, "bulkDeleteHistoryRuns").mockResolvedValue({
      deleted_count: 2,
      deleted_run_ids: ["r1", "r2"],
      missing_run_ids: [],
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    const el = document.createElement("div");
    document.body.appendChild(el);

    await act(async () => {
      renderHistoryPage(el);
    });

    await act(async () => {
      await Promise.resolve();
    });

    await switchToTable(el);

    const selectAll = el.querySelector(
      'input[aria-label="Select all visible runs"]',
    ) as HTMLInputElement;
    expect(selectAll).toBeTruthy();
    await act(async () => {
      selectAll.click();
    });

    const bulkBtn = [...el.querySelectorAll("button")].find((b) =>
      b.textContent?.startsWith("Delete ("),
    );
    expect(bulkBtn).toBeTruthy();

    await act(async () => {
      (bulkBtn as HTMLButtonElement).click();
      await Promise.resolve();
    });

    expect(api.bulkDeleteHistoryRuns).toHaveBeenCalledWith(["r1", "r2"]);
    expect(el.querySelector('a[href="/runs/r1"]')).toBeFalsy();
    expect(el.querySelector('a[href="/runs/r2"]')).toBeFalsy();
  });

  it("links table rows to the run page", async () => {
    vi.spyOn(api, "fetchHistoryRuns").mockResolvedValue([
      {
        run_id: "r1",
        ticker: "AAPL",
        date: "2026-05-01",
        rating: "Buy",
      },
    ]);

    const el = document.createElement("div");
    document.body.appendChild(el);

    await act(async () => {
      renderHistoryPage(el);
    });

    await act(async () => {
      await Promise.resolve();
    });

    await switchToTable(el);

    const openLink = el.querySelector('a[href="/runs/r1"]');
    expect(openLink).toBeTruthy();
    expect(openLink?.textContent).toMatch(/Open/);
    const stockLink = el.querySelector('a[href="/stocks/AAPL"]');
    expect(stockLink).toBeTruthy();
  });

});
