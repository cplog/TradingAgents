import type { HistoryRunDetail } from "../api";

const ANALYST_REPORT_KEYS = [
  "market",
  "social",
  "news",
  "fundamentals",
  "hot_money",
  "policy",
  "lockup",
  "kronos",
] as const;

const CONFIG_OVERRIDE_KEYS = [
  "llm_provider",
  "deep_think_llm",
  "quick_think_llm",
  "max_debate_rounds",
  "max_risk_discuss_rounds",
  "output_language",
  "openrouter_free_only",
  "backend_url",
  "llm_temperature",
  "dimensions_enabled",
  "dimensions_in_graph",
] as const;

/** Infer analyst ids from persisted snapshot or non-empty report sections. */
export function analystsFromHistoryDetail(detail: HistoryRunDetail): string[] {
  const snap = detail.config_snapshot?.analysts;
  if (Array.isArray(snap)) {
    const ids = snap.filter((x): x is string => typeof x === "string" && x.trim().length > 0);
    if (ids.length) return ids;
  }
  const coverage = detail.analyst_coverage;
  if (coverage && typeof coverage === "object") {
    const ids = Object.keys(coverage).filter((k) => k.trim().length > 0);
    if (ids.length) return ids;
  }
  const reports = detail.reports ?? {};
  return ANALYST_REPORT_KEYS.filter((k) => {
    const text = reports[k];
    return typeof text === "string" && text.trim().length > 0;
  });
}

/** Build POST /analyze body to re-run the same ticker/date with stored settings. */
export function buildRerunAnalyzePayload(detail: HistoryRunDetail): {
  ticker: string;
  date?: string;
  config_overrides?: Record<string, unknown>;
  analysts?: string[];
  report_format: "markdown";
} {
  const snap = detail.config_snapshot ?? {};
  const config_overrides: Record<string, unknown> = {};
  for (const key of CONFIG_OVERRIDE_KEYS) {
    if (key in snap && snap[key] !== undefined && snap[key] !== null) {
      config_overrides[key] = snap[key];
    }
  }
  const analysts = analystsFromHistoryDetail(detail);
  return {
    ticker: detail.ticker,
    date: detail.date || undefined,
    config_overrides: Object.keys(config_overrides).length ? config_overrides : undefined,
    analysts: analysts.length ? analysts : undefined,
    report_format: "markdown",
  };
}
