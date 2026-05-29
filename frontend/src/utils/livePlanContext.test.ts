import { describe, expect, it } from "vitest";
import {
  isInvalidatedStatus,
  livePracticalNote,
  type JobLiveContext,
} from "./livePlanContext";

const belowStopContext: JobLiveContext = {
  quote: {
    ticker: "MNSO",
    price: 13.1,
    currency: "USD",
    fetched_at: "2026-05-29T00:00:00Z",
  },
  report_close: 15.0,
  trade_date: "2026-05-25",
  levels: { entry: 15.1, stop_loss: 14.8, price_target: 16.8 },
  comparison: {
    status: "below_stop",
    guidance: "The tactical setup from this run is invalidated.",
    live_price: 13.1,
    entry: 15.1,
    stop_loss: 14.8,
    price_target: 16.8,
    delta_vs_entry_pct: -13.24,
    delta_vs_stop_pct: -11.49,
    delta_vs_target_pct: -22.02,
  },
};

describe("livePlanContext", () => {
  it("detects invalidated below-stop status", () => {
    expect(isInvalidatedStatus("below_stop")).toBe(true);
    expect(isInvalidatedStatus("below_entry")).toBe(false);
  });

  it("surfaces practical note from comparison guidance", () => {
    expect(livePracticalNote(belowStopContext)).toContain("invalidated");
  });
});
