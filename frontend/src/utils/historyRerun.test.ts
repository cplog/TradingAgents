import { describe, expect, it } from "vitest";
import { analystsFromHistoryDetail, buildRerunAnalyzePayload, buildRerunAnalyzePayloadFromJob } from "./historyRerun";
import type { HistoryRunDetail, JobStatus } from "../api";

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

  it("builds submit payload from failed job status", () => {
    const job: JobStatus = {
      job_id: "deadbeef",
      status: "failed",
      created_at: "2026-05-13T00:00:00Z",
      ticker: "NVDA",
      date: "2026-05-13",
      progress_events: [],
      resumable: false,
      analysts: ["market", "news"],
      trigger: "overnight_monitor",
      provenance: {
        llm_provider: "ollama-remote",
        llm_deep: "glm",
        llm_quick: "qwen",
        analysts_selected: ["market", "news"],
        analysts_ok: 0,
        analysts_empty: 0,
        analysts_failed: 0,
        analysts_total: 2,
        source_pillars: 4,
        vendor_count: 2,
        bias_warnings: [],
      },
    };
    const payload = buildRerunAnalyzePayloadFromJob(job);
    expect(payload.ticker).toBe("NVDA");
    expect(payload.analysts).toEqual(["market", "news"]);
    expect(payload.mode).toBe("scan");
    expect(payload.config_overrides?.llm_provider).toBe("ollama-remote");
  });
});
