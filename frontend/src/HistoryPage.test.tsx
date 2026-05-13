import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";
import { HistoryPage } from "./pages/HistoryPage";

describe("HistoryPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

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
      createRoot(el).render(
        <StrictMode>
          <MemoryRouter initialEntries={["/history"]}>
            <HistoryPage />
          </MemoryRouter>
        </StrictMode>
      );
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(el.innerHTML).toContain("History");
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
      createRoot(el).render(
        <StrictMode>
          <MemoryRouter>
            <HistoryPage />
          </MemoryRouter>
        </StrictMode>
      );
    });

    await act(async () => {
      await Promise.resolve();
    });

    const selects = el.querySelectorAll("select") as NodeListOf<HTMLSelectElement>;
    expect(selects.length).toBeGreaterThanOrEqual(2);
    await act(async () => {
      selects[0].value = "r1";
      selects[0].dispatchEvent(new Event("change", { bubbles: true }));
      selects[1].value = "r2";
      selects[1].dispatchEvent(new Event("change", { bubbles: true }));
    });

    const btn = [...el.querySelectorAll("button")].find((b) => b.textContent === "Compare");
    expect(btn).toBeTruthy();

    await act(async () => {
      (btn as HTMLButtonElement).click();
      await Promise.resolve();
    });

    expect(api.postHistoryCompare).toHaveBeenCalledWith("r1", "r2");
    expect(el.innerHTML).toContain("Side-by-side (A left · B right)");
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
      createRoot(el).render(
        <StrictMode>
          <MemoryRouter>
            <HistoryPage />
          </MemoryRouter>
        </StrictMode>
      );
    });

    await act(async () => {
      await Promise.resolve();
    });

    const deleteBtn = [...el.querySelectorAll("button")].find((b) => b.textContent === "Delete");
    expect(deleteBtn).toBeTruthy();

    await act(async () => {
      (deleteBtn as HTMLButtonElement).click();
      await Promise.resolve();
    });

    expect(api.deleteHistoryRun).toHaveBeenCalledWith("r1");
    expect(el.innerHTML).not.toContain("r1");
  });

  it("opens run detail from table", async () => {
    vi.spyOn(api, "fetchHistoryRuns").mockResolvedValue([
      {
        run_id: "r1",
        ticker: "AAPL",
        date: "2026-05-01",
        rating: "Buy",
      },
    ]);
    vi.spyOn(api, "fetchHistoryRun").mockResolvedValue({
      run_id: "r1",
      job_id: "r1",
      ticker: "AAPL",
      date: "2026-05-01",
      rating: "Buy",
      confidence: 0.9,
      reports: { market: "## Market\n\nDetails" },
      config_snapshot: {},
    });

    const el = document.createElement("div");
    document.body.appendChild(el);

    await act(async () => {
      createRoot(el).render(
        <StrictMode>
          <MemoryRouter>
            <HistoryPage />
          </MemoryRouter>
        </StrictMode>
      );
    });

    await act(async () => {
      await Promise.resolve();
    });

    const viewBtn = [...el.querySelectorAll("button")].find((b) => b.textContent === "View");
    expect(viewBtn).toBeTruthy();

    await act(async () => {
      (viewBtn as HTMLButtonElement).click();
      await Promise.resolve();
    });

    expect(api.fetchHistoryRun).toHaveBeenCalledWith("r1");
    expect(el.innerHTML).toContain("Run detail");
    expect(el.innerHTML).toContain("Details");
  });
});
