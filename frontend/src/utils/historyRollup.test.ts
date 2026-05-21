import { describe, expect, it } from "vitest";
import { groupRunsByTicker, relativeFromNow } from "./historyRollup";
import type { HistoryTableRow } from "./historyDisplay";

function row(overrides: Partial<HistoryTableRow> & { run_id: string }): HistoryTableRow {
  return {
    run_id: overrides.run_id,
    ticker: overrides.ticker ?? "AAPL",
    date: overrides.date ?? "2026-05-01",
    rating: overrides.rating ?? null,
    confidence: overrides.confidence ?? null,
    completed_at: overrides.completed_at ?? null,
    created_at: overrides.created_at ?? null,
    job_id: overrides.job_id ?? overrides.run_id,
    job_status: overrides.job_status ?? "completed",
    processing_at: overrides.processing_at ?? overrides.completed_at ?? null,
    is_live_job: overrides.is_live_job ?? false,
  };
}

describe("groupRunsByTicker", () => {
  it("groups runs by ticker and picks the newest processing time per group", () => {
    const rows: HistoryTableRow[] = [
      row({ run_id: "a1", ticker: "AAPL", processing_at: "2026-05-01T00:00:00Z", rating: "Hold" }),
      row({ run_id: "a2", ticker: "AAPL", processing_at: "2026-05-03T00:00:00Z", rating: "Buy" }),
      row({ run_id: "m1", ticker: "MSFT", processing_at: "2026-05-02T00:00:00Z", rating: "Hold" }),
    ];

    const groups = groupRunsByTicker(rows);

    // Sorted by most-recent processing time first → AAPL (5/3) then MSFT (5/2).
    expect(groups.map((g) => g.ticker)).toEqual(["AAPL", "MSFT"]);
    expect(groups[0].latestRun.run_id).toBe("a2");
    expect(groups[0].latestCompletedRun?.run_id).toBe("a2");
    expect(groups[0].runCount).toBe(2);
    expect(groups[0].completedRunCount).toBe(2);
    expect(groups[1].runCount).toBe(1);
  });

  it("flags an active status when any row in a group is running or queued", () => {
    const rows: HistoryTableRow[] = [
      row({ run_id: "done", ticker: "TSLA", processing_at: "2026-05-01T00:00:00Z", job_status: "completed" }),
      row({
        run_id: "live",
        ticker: "TSLA",
        processing_at: "2026-05-04T00:00:00Z",
        job_status: "running",
        rating: "…",
        is_live_job: true,
      }),
    ];

    const [g] = groupRunsByTicker(rows);
    expect(g.activeStatus).toBe("running");
    expect(g.latestCompletedRun?.run_id).toBe("done");
    expect(g.latestRun.run_id).toBe("live");
  });

  it("normalizes tickers to uppercase and uses '—' for missing", () => {
    const rows: HistoryTableRow[] = [
      row({ run_id: "x1", ticker: "aapl" }),
      row({ run_id: "x2", ticker: "" }),
      row({ run_id: "x3", ticker: null }),
    ];
    const groups = groupRunsByTicker(rows);
    const tickers = groups.map((g) => g.ticker).sort();
    expect(tickers).toContain("AAPL");
    expect(tickers).toContain("—");
  });
});

describe("relativeFromNow", () => {
  const now = Date.parse("2026-05-20T12:00:00Z");

  it("formats sub-minute, hour, day and month windows", () => {
    expect(relativeFromNow("2026-05-20T11:59:30Z", now)).toBe("30s ago");
    expect(relativeFromNow("2026-05-20T11:00:00Z", now)).toBe("1h ago");
    expect(relativeFromNow("2026-05-19T12:00:00Z", now)).toBe("yesterday");
    expect(relativeFromNow("2026-05-10T12:00:00Z", now)).toBe("10d ago");
    // 89 days ÷ 30-day-month approximation = 2mo.
    expect(relativeFromNow("2026-02-20T12:00:00Z", now)).toBe("2mo ago");
  });

  it("returns em dash for empty inputs", () => {
    expect(relativeFromNow(null, now)).toBe("—");
    expect(relativeFromNow(undefined, now)).toBe("—");
    expect(relativeFromNow("", now)).toBe("—");
  });
});
