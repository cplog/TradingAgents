import { describe, expect, it } from "vitest";
import type { JobResultPayload } from "../api";
import { extractVisualEvidence } from "./jobVisuals";

function baseResult(): JobResultPayload {
  return {
    ticker: "AAPL",
    date: "2026-05-20",
    rating: "Hold",
    reports: {},
    completed_at: "2026-05-20T00:00:00Z",
    structured: null,
    visual_artifacts: null,
  };
}

describe("extractVisualEvidence", () => {
  it("prefers visual_artifacts payloads when present", () => {
    const result = baseResult();
    result.visual_artifacts = {
      ohlcv_series: [
        { date: "2026-05-19", open: 100, high: 103, low: 99, close: 102, volume: 1200 },
      ],
      kronos_forecast: [{ date: "2026-05-21", point: 104, lower: 101, upper: 107 }],
      evidence_chain_xml: "<mxfile><diagram/></mxfile>",
    };
    const out = extractVisualEvidence(result);
    expect(out.ohlcvSeries).toHaveLength(1);
    expect(out.kronosForecast).toHaveLength(1);
    expect(out.evidenceChainXml).toContain("<mxfile>");
  });

  it("falls back to kronos_forecast history/forecast shape", () => {
    const result = baseResult() as JobResultPayload & { kronos_forecast?: unknown };
    result.kronos_forecast = {
      history_tail: [{ date: "2026-05-19", open: 100, high: 102, low: 99, close: 101, volume: 1000 }],
      forecast: [{ date: "2026-05-20", open: 101, high: 104, low: 100, close: 103, volume: 900 }],
    };
    const out = extractVisualEvidence(result);
    expect(out.ohlcvSeries).toHaveLength(1);
    expect(out.kronosForecast).toHaveLength(1);
  });

  it("caps very large arrays for render safety", () => {
    const result = baseResult();
    result.visual_artifacts = {
      ohlcv_series: Array.from({ length: 120 }, (_, i) => ({
        date: `2026-05-${String((i % 28) + 1).padStart(2, "0")}`,
        open: 100 + i,
        high: 101 + i,
        low: 99 + i,
        close: 100 + i,
      })),
      kronos_forecast: Array.from({ length: 90 }, (_, i) => ({
        date: `2026-06-${String((i % 28) + 1).padStart(2, "0")}`,
        open: 100 + i,
        high: 101 + i,
        low: 99 + i,
        close: 100 + i,
      })),
    };
    const out = extractVisualEvidence(result);
    expect(out.ohlcvSeries).toHaveLength(60);
    expect(out.kronosForecast).toHaveLength(30);
  });
});
