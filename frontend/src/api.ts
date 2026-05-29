/** API base: same origin in prod (served by FastAPI); Vite dev proxies /api, /analyze, … */

import type { StockDimensions, DimensionsCommentary } from './dimensions-types';
import type { JobLiveContext } from './utils/livePlanContext';

/** When Vite’s dev proxy misfires, set `VITE_API_ORIGIN=http://127.0.0.1:8808` in `frontend/.env.local`. */
export function resolveApiUrl(path: string): string {
  if (!path.startsWith("/")) return path;
  const raw =
    typeof import.meta !== "undefined" &&
    import.meta.env &&
    typeof import.meta.env.VITE_API_ORIGIN === "string"
      ? import.meta.env.VITE_API_ORIGIN.trim().replace(/\/$/, "")
      : "";
  return raw ? `${raw}${path}` : path;
}

function looksLikeHtmlDocument(body: string): boolean {
  const t = body.replace(/^\uFEFF/, "").trimStart();
  if (!t) return false;
  const head = t.slice(0, 512).toLowerCase();
  if (head.startsWith("<!doctype") || head.startsWith("<html")) return true;
  // BOM/whitespace-safe: JSON documents never start with '<' at the root.
  if (t[0] === "<") return true;
  return false;
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const url = resolveApiUrl(path);
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`${res.status}: ${text}`);
  }
  if (looksLikeHtmlDocument(text)) {
    const apiHint =
      path.startsWith("/api/") ||
      path.startsWith("/history") ||
      path.startsWith("/api/history") ||
      path.startsWith("/jobs") ||
      path.startsWith("/providers") ||
      path.startsWith("/dimensions")
        ? "Start the FastAPI API on port 8808 (e.g. `uvicorn api.main:app --port 8808`) so Vite can proxy this path. "
        : "";
    throw new Error(
      `Expected JSON from ${url}, got HTML (usually index.html: API not reached). ${apiHint}` +
        `If you use \`vite preview\`, set the same \`preview.proxy\` as dev (see frontend/vite.config.ts).` +
        (typeof import.meta !== "undefined" && import.meta.env?.DEV
          ? " Or set VITE_API_ORIGIN=http://127.0.0.1:8808 in frontend/.env.local to bypass the proxy."
          : ""),
    );
  }
  try {
    return JSON.parse(text) as T;
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg.includes("Unexpected token") && text.trimStart().startsWith("<")) {
      throw new Error(
        `Expected JSON from ${url}, got HTML/markup. Start the API on :8808 or fix the dev proxy. First bytes: ${JSON.stringify(text.slice(0, 160))}`
      );
    }
    throw new Error(`${msg} (response from ${url}, first bytes: ${JSON.stringify(text.slice(0, 120))})`);
  }
}

export type HealthPayload = {
  ok: boolean;
  llm_provider: string;
  api_key_configured: boolean;
  state_store: string;
  cloudflare_kv_configured: boolean;
  data_cache_dir: string;
  results_dir: string;
  yfinance_reachable: boolean | null;
  /** Present on current API builds; when missing, assume legacy core-four-only analysts. */
  supported_analyst_ids?: string[];
  data_source_checks?: Record<
    string,
    {
      ok: boolean;
      configured: boolean;
      checked_at: string;
      detail?: string | null;
    }
  >;
};

export async function fetchHealth(): Promise<HealthPayload> {
  return apiJson<HealthPayload>("/api/health");
}

/**
 * Intersect selected analysts with what the server explicitly reports.
 * When capabilities are unknown (`null`/`undefined`/empty list), send the full selection — do not guess "core four only"
 * (that caused false positives when /api/health omitted the field while POST /analyze already accepted eight analysts).
 */
export function filterAnalystsForBackend(
  selected: string[],
  supportedFromHealth: string[] | null | undefined
): { analysts: string[] | undefined; dropped: string[] } {
  if (!selected.length) return { analysts: undefined, dropped: [] };
  if (
    supportedFromHealth === undefined ||
    supportedFromHealth === null ||
    supportedFromHealth.length === 0
  ) {
    return { analysts: selected, dropped: [] };
  }
  const allow = new Set(supportedFromHealth);
  const dropped: string[] = [];
  const kept: string[] = [];
  for (const id of selected) {
    if (allow.has(id)) kept.push(id);
    else dropped.push(id);
  }
  return { analysts: kept.length ? kept : undefined, dropped };
}

export async function fetchConfig(): Promise<Record<string, unknown>> {
  return apiJson("/config");
}

/**
 * Analyst ids this API build accepts. Health may omit the field (proxies); /config includes it as fallback.
 */
export function mergeSupportedAnalystIds(
  health: HealthPayload | null,
  config: Record<string, unknown> | null
): string[] | null {
  const fromHealth = health?.supported_analyst_ids;
  if (Array.isArray(fromHealth) && fromHealth.length > 0) {
    return fromHealth.map((x) => String(x));
  }
  const fromCfg = config?.supported_analyst_ids;
  if (Array.isArray(fromCfg) && fromCfg.length > 0) {
    return fromCfg.map((x) => String(x));
  }
  return null;
}

export type ProviderModel = {
  id: string;
  label: string;
  loaded?: boolean | null;
  is_free?: boolean | null;
};

export async function fetchProviderModels(
  provider: string,
  backendUrl?: string
): Promise<{ provider: string; source: string; models: ProviderModel[] }> {
  const qs = new URLSearchParams();
  if (backendUrl && backendUrl.trim()) qs.set("backend_url", backendUrl.trim());
  const suffix = qs.size ? `?${qs.toString()}` : "";
  return apiJson(`/providers/${encodeURIComponent(provider)}/models${suffix}`);
}

/** Future PRODUCT.md visuals — optional fields when backend adds them. */
export type JobVisualArtifacts = {
  ohlcv_series?: { date: string; open: number; high: number; low: number; close: number; volume?: number }[];
  kronos_forecast?: { date: string; point: number; lower?: number; upper?: number }[];
  evidence_chain_xml?: string | null;
};

export type JobResultPayload = {
  ticker: string;
  date: string;
  rating: string;
  confidence?: number | null;
  reports: Record<string, string>;
  /** Optional chart/map payloads (not yet populated by default API builds). */
  visual_artifacts?: JobVisualArtifacts | null;
  /** Present when the job used explicit analyst selection (API path). */
  analyst_coverage?: Record<
    string,
    { status: string; section_key?: string; chars?: number; detail?: string }
  > | null;
  structured?: Record<string, unknown> | null;
  artifacts_path?: string | null;
  completed_at: string;
  dimensions?: StockDimensions | null;
  dimensions_commentary?: DimensionsCommentary | null;
  dimensions_error?: string | null;
  dimensions_in_graph?: boolean | null;
  confidence_raw_tier?: number | null;
  confidence_breakdown?: {
    tier?: number;
    coherence_penalty?: number;
    data_quality_penalty?: number;
    peer_penalty?: number;
  } | null;
  confidence_inputs?: {
    supporting_factors?: { key: string; score: number }[];
    conflicting_factors?: { key: string; score: number }[];
    weak_data?: string[];
    peer_scope?: string | null;
  } | null;
};

export type JobDimensionsBundle = {
  dimensions: StockDimensions | null;
  commentary: DimensionsCommentary | null;
  error: string | null;
};

export type JobStatus = {
  job_id: string;
  status: string;
  created_at: string;
  ticker?: string | null;
  date?: string | null;
  result?: JobResultPayload | null;
  error?: string | null;
  progress_events: { ts: string; stage: string; message: string; details?: string }[];
  batch_id?: string | null;
  resumable?: boolean;
  last_graph_step?: number | null;
  checkpoint_thread_id?: string | null;
  provenance?: RunProvenance | null;
  trigger?: string | null;
  signal_score?: number | null;
  analysts?: string[];
};

export type AnalyzeRequestBody = {
  ticker: string;
  date?: string;
  config_overrides?: Record<string, unknown>;
  analysts?: string[];
  report_format?: "markdown" | "json" | "structured";
  mode?: "scan" | "full";
};

export async function submitAnalyze(body: AnalyzeRequestBody): Promise<{ job_id: string; status: string; created_at: string }> {
  return apiJson("/analyze", { method: "POST", body: JSON.stringify(body) });
}

export async function getJob(jobId: string): Promise<JobStatus> {
  return apiJson(`/jobs/${jobId}`);
}

export async function resumeJob(jobId: string): Promise<{
  job_id: string;
  status: string;
  resumable: boolean;
  last_graph_step?: number | null;
  message: string;
}> {
  return apiJson(`/jobs/${jobId}/resume`, { method: "POST" });
}

export async function fetchJobs(limit = 50, status?: string): Promise<JobStatus[]> {
  const qs = new URLSearchParams({ limit: String(limit) });
  if (status) qs.set("status", status);
  return apiJson(`/jobs?${qs.toString()}`);
}

export async function submitBatch(body: {
  tickers: string[];
  date?: string;
  config_overrides?: Record<string, unknown>;
  analysts?: string[];
}): Promise<{ batch_id: string; job_ids: string[]; created_at: string }> {
  return apiJson("/batches", { method: "POST", body: JSON.stringify(body) });
}

export async function getBatch(batchId: string): Promise<{
  batch_id: string;
  jobs: JobStatus[];
  summary: Record<string, number>;
}> {
  return apiJson(`/batches/${batchId}`);
}

export type NewsSource =
  | "yfinance"
  | "yfinance_macro"
  | "finnhub"
  | "google_rss"
  | "akshare"
  | "reddit"
  | "stocktwits"
  | "alpha_vantage";

export type NewsItem = {
  title: string;
  summary: string;
  publisher: string;
  link: string;
  pub_date: string | null;
  ticker: string;
  sentiment: "bullish" | "bearish" | "neutral";
  sentiment_score: number;
  sector_tags: string[];
  source: NewsSource;
};

export type NewsFeedPayload = {
  items: NewsItem[];
  ticker: string;
  fetched_at?: string;
  source_errors?: Record<string, string>;
};

export async function fetchNews(ticker: string, limit = 50): Promise<NewsFeedPayload> {
  return apiJson<NewsFeedPayload>(
    `/news/${encodeURIComponent(ticker)}?limit=${limit}`
  );
}

export function openJobEvents(jobId: string): EventSource {
  return new EventSource(resolveApiUrl(`/jobs/${jobId}/events`));
}

export async function postRuntimeConfig(
  body: {
    service_overrides?: Record<string, unknown>;
    secrets?: Record<string, string>;
  },
  adminKey: string
): Promise<void> {
  const res = await fetch(resolveApiUrl("/admin/runtime-config"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Key": adminKey,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
}

export type RunProvenance = {
  llm_provider?: string | null;
  llm_deep?: string | null;
  llm_quick?: string | null;
  data_routing?: string | null;
  analysts_selected?: string[];
  analysts_ok?: number;
  analysts_empty?: number;
  analysts_failed?: number;
  analysts_total?: number;
  source_pillars?: number;
  vendor_count?: number;
  bias_warnings?: string[];
};

export type HistoryRunRef = {
  run_id: string;
  job_id?: string | null;
  ticker?: string | null;
  date?: string | null;
  rating?: string | null;
  confidence?: number | null;
  completed_at?: string | null;
  created_at?: string | null;
  batch_id?: string | null;
  factor_scores?: Record<string, number> | null;
  facts_sector?: string | null;
  facts_industry?: string | null;
  has_dimensions?: boolean | null;
  has_commentary?: boolean | null;
  provenance?: RunProvenance | null;
};

/** Aggregated persisted-run counts per sector/industry (D1 history only). */
export type HistoryCoverageRow = {
  sector: string;
  industry: string;
  run_count: number;
  with_dimensions_count: number;
  with_commentary_count: number;
  latest_completed_at?: string | null;
};

/** Catalog constituent with optional latest persisted analysis coverage. */
export type IndustryConstituentRow = {
  ticker: string;
  market: string;
  run_count: number;
  has_report: boolean;
  has_dimensions: boolean;
  has_commentary: boolean;
  latest_rating?: string | null;
  latest_date?: string | null;
  latest_run_id?: string | null;
  latest_completed_at?: string | null;
};

export type HistoryRunDetail = {
  run_id: string;
  job_id: string;
  ticker: string;
  date: string;
  rating: string;
  confidence?: number | null;
  reports: Record<string, string>;
  structured?: Record<string, unknown> | null;
  artifacts_path?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
  batch_id?: string | null;
  config_snapshot: Record<string, unknown>;
  provenance?: RunProvenance | null;
  analyst_coverage?: Record<string, { status?: string; section_key?: string }> | null;
  dimensions?: StockDimensions | null;
  dimensions_commentary?: DimensionsCommentary | null;
  dimensions_error?: string | null;
  dimensions_in_graph?: boolean | null;
};

export type HistoryCompareSide = {
  run_id?: string | null;
  job_id?: string | null;
  ticker?: string | null;
  date?: string | null;
  rating?: string | null;
  confidence?: number | null;
  completed_at?: string | null;
  created_at?: string | null;
  config_snapshot: Record<string, unknown>;
  reports: Record<string, string>;
  structured?: Record<string, unknown> | null;
  artifacts_path?: string | null;
  excerpt_portfolio_decision: string;
  excerpt_trader_plan: string;
};

export type HistoryCompareResponse = {
  a: HistoryCompareSide;
  b: HistoryCompareSide;
};

export async function fetchHistoryRuns(params?: {
  ticker?: string;
  limit?: number;
  date_from?: string;
  date_to?: string;
  sector?: string;
  industry?: string;
}): Promise<HistoryRunRef[]> {
  const qs = new URLSearchParams();
  if (params?.ticker?.trim()) qs.set("ticker", params.ticker.trim());
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.date_from?.trim()) qs.set("date_from", params.date_from.trim());
  if (params?.date_to?.trim()) qs.set("date_to", params.date_to.trim());
  if (params?.sector?.trim()) qs.set("sector", params.sector.trim());
  if (params?.industry?.trim()) qs.set("industry", params.industry.trim());
  const suffix = qs.size ? `?${qs.toString()}` : "";
  return apiJson<HistoryRunRef[]>(`/api/history/runs${suffix}`);
}

export async function fetchHistoryCoverage(): Promise<HistoryCoverageRow[]> {
  return apiJson<HistoryCoverageRow[]>("/api/history/coverage");
}

/** Yahoo sector/industry catalog freshness — counts + newest updated_at. */
export type CatalogStatus = {
  d1_enabled: boolean;
  buckets: number;
  constituents_total: number;
  constituents_us: number;
  constituents_hk: number;
  /** POSIX seconds (server time) of newest bucket row's updated_at. */
  latest_bucket_refreshed_at?: number | null;
  /** POSIX seconds (server time) of newest constituent row's updated_at. */
  latest_constituent_refreshed_at?: number | null;
};

export async function fetchCatalogStatus(): Promise<CatalogStatus> {
  return apiJson<CatalogStatus>("/api/catalog/status");
}

export async function fetchIndustryConstituents(params: {
  sector: string;
  industry: string;
  market?: string;
}): Promise<IndustryConstituentRow[]> {
  const qs = new URLSearchParams();
  qs.set("sector", params.sector.trim());
  qs.set("industry", params.industry.trim());
  if (params.market?.trim()) qs.set("market", params.market.trim().toUpperCase());
  const q = qs.toString();
  const paths = [
    `/api/catalog/industry-constituents?${q}`,
    `/api/history/constituents?${q}`,
  ];
  let lastErr: Error | null = null;
  for (const path of paths) {
    try {
      return await apiJson<IndustryConstituentRow[]>(path);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      lastErr = e instanceof Error ? e : new Error(msg);
      if (msg.startsWith("404:") && path !== paths[paths.length - 1]) {
        continue;
      }
      if (msg.startsWith("404:") && path === paths[paths.length - 1]) {
        throw new Error(
          `${msg}\n` +
            "If the API is running, the Vite dev proxy may be returning this 404. " +
            "Create frontend/.env.local with VITE_API_ORIGIN=http://127.0.0.1:8808 (or your API port), restart npm run dev, and try again. " +
            "Verify the route exists: curl -sS 'http://127.0.0.1:8808/openapi.json' | grep industry-constituents",
        );
      }
      throw lastErr;
    }
  }
  throw lastErr ?? new Error("Failed to load industry constituents");
}

export async function fetchHistoryRun(runId: string): Promise<HistoryRunDetail> {
  return apiJson<HistoryRunDetail>(
    `/api/history/runs/${encodeURIComponent(runId)}`
  );
}

export async function deleteHistoryRun(runId: string): Promise<{ deleted: boolean; run_id: string }> {
  return apiJson<{ deleted: boolean; run_id: string }>(
    `/api/history/runs/${encodeURIComponent(runId)}`,
    {
      method: "DELETE",
    }
  );
}

export async function bulkDeleteHistoryRuns(runIds: string[]): Promise<{
  deleted_count: number;
  deleted_run_ids: string[];
  missing_run_ids: string[];
  scope?: string;
}> {
  return apiJson("/api/history/runs/bulk-delete", {
    method: "POST",
    body: JSON.stringify({ run_ids: runIds }),
  });
}

export async function deleteAllHistoryRuns(body: {
  confirm: boolean;
  ticker?: string;
  date_from?: string;
  date_to?: string;
}): Promise<{
  deleted_count: number;
  deleted_run_ids: string[];
  missing_run_ids: string[];
  scope?: string;
}> {
  return apiJson("/api/history/runs/delete-all", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function postHistoryCompare(runIdA: string, runIdB: string): Promise<HistoryCompareResponse> {
  return apiJson<HistoryCompareResponse>("/api/history/compare", {
    method: "POST",
    body: JSON.stringify({ run_id_a: runIdA, run_id_b: runIdB }),
  });
}

export async function postClearCache(adminKey: string, mode = "checkpoints"): Promise<unknown> {
  const res = await fetch(resolveApiUrl("/admin/cache/clear"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Key": adminKey,
    },
    body: JSON.stringify({ mode }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getJobLiveContext(jobId: string): Promise<JobLiveContext> {
  return apiJson(`/api/jobs/${encodeURIComponent(jobId)}/live-context`);
}

export async function getHistoryRunLiveContext(runId: string): Promise<JobLiveContext> {
  return apiJson(`/api/history/runs/${encodeURIComponent(runId)}/live-context`);
}

export async function getJobDimensions(jobId: string): Promise<JobDimensionsBundle> {
  const r = await fetch(resolveApiUrl(`/jobs/${jobId}/dimensions`));
  if (!r.ok) {
    throw new Error(`getJobDimensions failed: ${r.status}`);
  }
  const raw = (await r.json()) as unknown;
  if (raw && typeof raw === "object") {
    const o = raw as Record<string, unknown>;
    if ("dimensions" in o || "commentary" in o || "error" in o) {
      return {
        dimensions: (o.dimensions ?? null) as StockDimensions | null,
        commentary: (o.commentary ?? null) as DimensionsCommentary | null,
        error: (typeof o.error === "string" ? o.error : null) as string | null,
      };
    }
  }
  if (raw && typeof raw === "object" && "ticker" in raw && "factor_scores" in raw) {
    return { dimensions: raw as StockDimensions, commentary: null, error: null };
  }
  return { dimensions: null, commentary: null, error: null };
}

export async function getDimensionsByTicker(
  ticker: string, asOfDate?: string,
): Promise<StockDimensions> {
  const url = asOfDate
    ? `/api/dimensions/${encodeURIComponent(ticker)}?as_of_date=${encodeURIComponent(asOfDate)}`
    : `/api/dimensions/${encodeURIComponent(ticker)}`;
  return apiJson<StockDimensions>(url);
}

export async function cancelJob(jobId: string): Promise<{ cancellation_requested: boolean; status: string }> {
  const r = await fetch(resolveApiUrl(`/jobs/${jobId}/cancel`), { method: 'POST' });
  if (!r.ok) throw new Error(`cancelJob failed: ${r.status}`);
  return r.json();
}

export async function recomputeDimensions(runId: string) {
  return apiJson<HistoryRunDetail>(
    `/api/history/runs/${encodeURIComponent(runId)}/recompute-dimensions`,
    { method: "POST" }
  );
}

export type MonitorStatus = {
  enabled: boolean;
  session: string;
  should_poll: boolean;
  poll_seconds: number;
  threshold: number;
  watchlist: string[];
  last_tick: string | null;
  last_candidates: string[];
  last_errors: string[];
  cooldown_tickers: string[];
};

export type MonitorSignal = {
  ticker: string;
  score: number;
  job_id?: string;
  at?: string;
  change_pct?: number | null;
};

export async function fetchMonitorStatus(): Promise<MonitorStatus> {
  return apiJson("/api/monitor/status");
}

export async function fetchMonitorWatchlist(): Promise<{ tickers: string[] }> {
  return apiJson("/api/monitor/watchlist");
}

export async function setMonitorWatchlist(tickers: string[]): Promise<{ tickers: string[] }> {
  return apiJson("/api/monitor/watchlist", {
    method: "PUT",
    body: JSON.stringify({ tickers }),
  });
}

export async function addMonitorWatchlistTicker(ticker: string): Promise<{ tickers: string[] }> {
  return apiJson("/api/monitor/watchlist", {
    method: "POST",
    body: JSON.stringify({ ticker }),
  });
}

export async function removeMonitorWatchlistTicker(ticker: string): Promise<{ tickers: string[] }> {
  return apiJson(`/api/monitor/watchlist/${encodeURIComponent(ticker)}`, {
    method: "DELETE",
  });
}

export async function fetchMonitorSignals(limit = 50): Promise<{ signals: MonitorSignal[] }> {
  return apiJson(`/api/monitor/signals?limit=${limit}`);
}

export async function triggerMonitorTick(): Promise<Record<string, unknown>> {
  return apiJson("/api/monitor/tick", { method: "POST" });
}

// --- Topics (Hot Ideas) ---

export type TopicCadence = "daily" | "weekly" | "manual";
export type TopicSource = "seed" | "user";
export type TickerMarket = "us" | "hk" | "cn" | "other";

export type TickerCandidate = {
  ticker: string;
  company_name?: string | null;
  confidence: number;
  rationale?: string | null;
  market: TickerMarket;
};

export type TopicArticle = {
  title: string;
  url: string;
  snippet?: string | null;
  published_at?: string | null;
  source?: string | null;
};

export type TopicRun = {
  run_id: string;
  topic_id: string;
  started_at: string;
  completed_at?: string | null;
  status: "running" | "completed" | "failed";
  articles: TopicArticle[];
  candidates: TickerCandidate[];
  theme_summary?: string | null;
  error?: string | null;
};

export type TopicSummary = {
  id: string;
  label: string;
  query: string;
  cadence: TopicCadence;
  pinned: boolean;
  source: TopicSource;
  last_run_at?: string | null;
  candidate_count: number;
  top_candidates: TickerCandidate[];
};

export type Topic = {
  id: string;
  label: string;
  query: string;
  cadence: TopicCadence;
  pinned: boolean;
  source: TopicSource;
  created_at: string;
  updated_at: string;
  last_run_at?: string | null;
  last_refresh_at?: string | null;
};

export type TopicDetail = {
  topic: Topic;
  latest_run: TopicRun | null;
};

export async function fetchTopics(): Promise<{ topics: TopicSummary[] }> {
  return apiJson("/api/topics");
}

export async function fetchTopic(id: string): Promise<TopicDetail> {
  return apiJson(`/api/topics/${encodeURIComponent(id)}`);
}

export async function fetchTopicRuns(id: string): Promise<{ runs: TopicRun[] }> {
  return apiJson(`/api/topics/${encodeURIComponent(id)}/runs`);
}

export async function searchTopic(body: {
  query: string;
  label?: string;
  cadence?: TopicCadence;
}): Promise<TopicDetail> {
  return apiJson("/api/topics/search", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function refreshTopic(id: string): Promise<{ run: TopicRun }> {
  return apiJson(`/api/topics/${encodeURIComponent(id)}/refresh`, { method: "POST" });
}

export async function updateTopic(
  id: string,
  body: { label?: string; query?: string; cadence?: TopicCadence },
): Promise<TopicDetail> {
  return apiJson(`/api/topics/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function pinTopic(id: string): Promise<TopicDetail> {
  return apiJson(`/api/topics/${encodeURIComponent(id)}/pin`, { method: "POST" });
}

export async function unpinTopic(id: string): Promise<TopicDetail> {
  return apiJson(`/api/topics/${encodeURIComponent(id)}/pin`, { method: "DELETE" });
}

export async function deleteTopic(id: string): Promise<{ deleted: string }> {
  return apiJson(`/api/topics/${encodeURIComponent(id)}`, { method: "DELETE" });
}
