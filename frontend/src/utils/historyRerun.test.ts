import { describe, expect, it } from "vitest";
import { analystsFromHistoryDetail, buildRerunAnalyzePayload } from "./historyRerun";
import type { HistoryRunDetail } from "../api";

function baseDetail(overrides: Partial<HistoryRunDetail> = {}): HistoryRunDetail {
  return {
    run_id: "abc123",
    job_id: "abc123",
    ticker: "AAPL",
    date: "2026-05-13",
    rating: "Buy",
    reports: {
      market: "m",
      social: "s",
      news: "n",
      fundamentals: "f",
    },
    config_snapshot: {
      llm_provider: "openrouter",
      quick_think_llm: "test-model",
      max_debate_rounds: 2,
    },
    ...overrides,
  };
}

describe("historyRerun", () => {
  it("prefers analysts from config_snapshot", () => {
    const detail = baseDetail({
      config_snapshot: { analysts: ["market", "kronos"] },
      reports: { market: "x" },
    });
    expect(analystsFromHistoryDetail(detail)).toEqual(["market", "kronos"]);
  });

  it("falls back to non-empty analyst report sections", () => {
    const detail = baseDetail({
      config_snapshot: {},
      reports: { market: "x", kronos: "k", research_plan: "skip" },
    });
    expect(analystsFromHistoryDetail(detail)).toEqual(["market", "kronos"]);
  });

  it("builds submit payload from history detail", () => {
    const payload = buildRerunAnalyzePayload(
      baseDetail({ config_snapshot: { analysts: ["market"], llm_provider: "openai" } }),
    );
    expect(payload.ticker).toBe("AAPL");
    expect(payload.date).toBe("2026-05-13");
    expect(payload.analysts).toEqual(["market"]);
    expect(payload.config_overrides?.llm_provider).toBe("openai");
    expect(payload.report_format).toBe("markdown");
  });
});
