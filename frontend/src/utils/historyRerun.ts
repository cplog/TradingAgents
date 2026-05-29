import type { AnalyzeRequestBody, HistoryRunDetail, JobStatus } from "../api";
import { llmConfigToOverrides, type LlmConfig } from "../components/LlmPicker";

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
export function buildRerunAnalyzePayload(detail: HistoryRunDetail): AnalyzeRequestBody {
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

/** Build POST /analyze from a live/failed job row (no persisted history detail). */
export function buildRerunAnalyzePayloadFromJob(job: JobStatus): AnalyzeRequestBody {
  const prov = job.provenance;
  const config_overrides: Record<string, unknown> = {};
  if (prov?.llm_provider) config_overrides.llm_provider = prov.llm_provider;
  if (prov?.llm_deep) config_overrides.deep_think_llm = prov.llm_deep;
  if (prov?.llm_quick) config_overrides.quick_think_llm = prov.llm_quick;

  const analysts =
    job.analysts && job.analysts.length
      ? job.analysts
      : prov?.analysts_selected?.length
        ? prov.analysts_selected
        : undefined;

  const ticker = (job.ticker ?? "").trim();
  if (!ticker) {
    throw new Error("Job has no ticker");
  }

  const body: AnalyzeRequestBody = {
    ticker,
    date: job.date || undefined,
    config_overrides: Object.keys(config_overrides).length ? config_overrides : undefined,
    analysts,
    report_format: "markdown",
  };

  if (job.trigger === "scan" || job.trigger === "overnight_monitor") {
    body.mode = "scan";
  }

  return body;
}

/** Map persisted run config into LlmPicker fields (for “copy from previous run”). */
export function llmConfigFromSnapshot(
  snap: Record<string, unknown> | null | undefined,
): Partial<LlmConfig> {
  if (!snap || typeof snap !== "object") return {};
  const partial: Partial<LlmConfig> = {};
  const prov = snap.llm_provider;
  if (typeof prov === "string" && prov.trim()) {
    partial.provider = prov === "ollama" ? "ollama-local" : prov;
  }
  if (typeof snap.deep_think_llm === "string" && snap.deep_think_llm.trim()) {
    partial.deepModel = snap.deep_think_llm;
  }
  if (typeof snap.quick_think_llm === "string" && snap.quick_think_llm.trim()) {
    partial.quickModel = snap.quick_think_llm;
  }
  if (typeof snap.backend_url === "string") {
    partial.backendUrl = snap.backend_url;
  }
  if (typeof snap.openrouter_free_only === "boolean") {
    partial.openrouterFreeOnly = snap.openrouter_free_only;
  }
  return partial;
}

/** Human-readable prior-run LLM line for the rerun dialog. */
export function formatPriorRunLlmLabel(
  snap: Record<string, unknown> | null | undefined,
  provenance?: { llm_provider?: string | null; llm_deep?: string | null; llm_quick?: string | null } | null,
): string | null {
  const prov =
    (typeof snap?.llm_provider === "string" && snap.llm_provider) ||
    provenance?.llm_provider ||
    null;
  const deep =
    (typeof snap?.deep_think_llm === "string" && snap.deep_think_llm) ||
    provenance?.llm_deep ||
    null;
  const quick =
    (typeof snap?.quick_think_llm === "string" && snap.quick_think_llm) ||
    provenance?.llm_quick ||
    null;
  if (!prov && !deep && !quick) return null;
  const models =
    deep && quick && deep !== quick ? `${deep} / ${quick}` : deep || quick || "";
  return models ? `${prov ?? "unknown"} · ${models}` : String(prov);
}

/** Apply the user’s LLM picker choice onto a rerun / retry analyze body. */
export function withLlmOverrides(
  body: AnalyzeRequestBody,
  llm: LlmConfig,
): AnalyzeRequestBody {
  return {
    ...body,
    config_overrides: {
      ...(body.config_overrides ?? {}),
      ...llmConfigToOverrides(llm),
    },
  };
}
