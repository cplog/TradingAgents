import { describe, expect, it } from "vitest";
import {
  formatHistoryTimestampWithZone,
  mergeHistoryAndJobs,
  sortHistoryRows,
} from "./historyDisplay";

describe("historyDisplay", () => {
  it("merges in-progress jobs with persisted history", () => {
    const rows = mergeHistoryAndJobs(
      [
        {
          run_id: "done1",
          ticker: "AAPL",
          date: "2026-05-01",
          rating: "Buy",
          completed_at: "2026-05-01T10:00:00Z",
        },
      ],
      [
        {
          job_id: "live9",
          status: "running",
          created_at: "2026-05-19T12:00:00Z",
          ticker: "NVDA",
          date: "2026-05-19",
          progress_events: [],
        },
      ],
    );
    expect(rows).toHaveLength(2);
    const live = rows.find((r) => r.run_id === "live9");
    expect(live?.job_status).toBe("running");
    expect(live?.is_live_job).toBe(true);
  });

  it("defaults sort to newest processing time first", () => {
    const rows = sortHistoryRows(
      mergeHistoryAndJobs(
        [
          {
            run_id: "old",
            completed_at: "2026-05-01T10:00:00Z",
          },
          {
            run_id: "new",
            completed_at: "2026-05-19T10:00:00Z",
          },
        ],
        [],
      ),
      "processing_desc",
    );
    expect(rows[0]?.run_id).toBe("new");
  });

  it("formats timestamps in HKT label", () => {
    const text = formatHistoryTimestampWithZone("2026-05-19T04:30:00Z");
    expect(text).toContain("HKT");
    expect(text).not.toBe("—");
  });
});
