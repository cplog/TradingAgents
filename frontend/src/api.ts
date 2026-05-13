/** API base: same origin in prod (served by FastAPI); Vite dev proxies /api, /analyze, … */

import type { StockDimensions } from './dimensions-types';

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
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`${res.status}: ${text}`);
  }
  if (looksLikeHtmlDocument(text)) {
    const apiHint =
      path.startsWith("/history") || path.startsWith("/jobs") || path.startsWith("/providers")
        ? "Start the FastAPI API on port 8000 (e.g. `uvicorn api.main:app --port 8000`) so Vite can proxy this path. "
        : "";
    throw new Error(
      `Expected JSON from ${path}, got HTML (usually index.html: API not reached). ${apiHint}` +
        `If you use \`vite preview\`, set the same \`preview.proxy\` as dev (see frontend/vite.config.ts).`
    );
  }
  try {
    return JSON.parse(text) as T;
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg.includes("Unexpected token") && text.trimStart().startsWith("<")) {
      throw new Error(
        `Expected JSON from ${path}, got HTML/markup. Start the API on :8000 or fix the dev proxy. First bytes: ${JSON.stringify(text.slice(0, 160))}`
      );
    }
    throw new Error(`${msg} (response from ${path}, first bytes: ${JSON.stringify(text.slice(0, 120))})`);
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
};

export async function fetchHealth(): Promise<HealthPayload> {
  return apiJson<HealthPayload>("/api/health");
}

export async function fetchConfig(): Promise<Record<string, unknown>> {
  return apiJson("/config");
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

export type JobStatus = {
  job_id: string;
  status: string;
  created_at: string;
  ticker?: string | null;
  date?: string | null;
  result?: {
    ticker: string;
    date: string;
    rating: string;
    confidence?: number | null;
    reports: Record<string, string>;
    artifacts_path?: string | null;
    completed_at: string;
  } | null;
  error?: string | null;
  progress_events: { ts: string; stage: string; message: string; details?: string }[];
  batch_id?: string | null;
};

export async function submitAnalyze(body: {
  ticker: string;
  date?: string;
  config_overrides?: Record<string, unknown>;
  analysts?: string[];
  report_format?: "markdown" | "json" | "structured";
}): Promise<{ job_id: string; status: string; created_at: string }> {
  return apiJson("/analyze", { method: "POST", body: JSON.stringify(body) });
}

export async function getJob(jobId: string): Promise<JobStatus> {
  return apiJson(`/jobs/${jobId}`);
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
  return new EventSource(`/jobs/${jobId}/events`);
}

export async function postRuntimeConfig(
  body: {
    service_overrides?: Record<string, unknown>;
    secrets?: Record<string, string>;
  },
  adminKey: string
): Promise<void> {
  const res = await fetch("/admin/runtime-config", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Key": adminKey,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
}

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
}): Promise<HistoryRunRef[]> {
  const qs = new URLSearchParams();
  if (params?.ticker?.trim()) qs.set("ticker", params.ticker.trim());
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.date_from?.trim()) qs.set("date_from", params.date_from.trim());
  if (params?.date_to?.trim()) qs.set("date_to", params.date_to.trim());
  const suffix = qs.size ? `?${qs.toString()}` : "";
  return apiJson<HistoryRunRef[]>(`/history/runs${suffix}`);
}

export async function fetchHistoryRun(runId: string): Promise<HistoryRunDetail> {
  return apiJson<HistoryRunDetail>(`/history/runs/${encodeURIComponent(runId)}`);
}

export async function deleteHistoryRun(runId: string): Promise<{ deleted: boolean; run_id: string }> {
  return apiJson<{ deleted: boolean; run_id: string }>(`/history/runs/${encodeURIComponent(runId)}`, {
    method: "DELETE",
  });
}

export async function postHistoryCompare(runIdA: string, runIdB: string): Promise<HistoryCompareResponse> {
  return apiJson<HistoryCompareResponse>("/history/compare", {
    method: "POST",
    body: JSON.stringify({ run_id_a: runIdA, run_id_b: runIdB }),
  });
}

export async function postClearCache(adminKey: string, mode = "checkpoints"): Promise<unknown> {
  const res = await fetch("/admin/cache/clear", {
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

export async function getJobDimensions(jobId: string): Promise<StockDimensions> {
  const r = await fetch(`/jobs/${jobId}/dimensions`);
  if (!r.ok) throw new Error(`getJobDimensions failed: ${r.status}`);
  return r.json();
}

export async function getDimensionsByTicker(
  ticker: string, asOfDate?: string,
): Promise<StockDimensions> {
  const url = asOfDate
    ? `/dimensions/${encodeURIComponent(ticker)}?as_of_date=${asOfDate}`
    : `/dimensions/${encodeURIComponent(ticker)}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`getDimensionsByTicker failed: ${r.status}`);
  return r.json();
}

export async function cancelJob(jobId: string): Promise<{ cancellation_requested: boolean; status: string }> {
  const r = await fetch(`/jobs/${jobId}/cancel`, { method: 'POST' });
  if (!r.ok) throw new Error(`cancelJob failed: ${r.status}`);
  return r.json();
}

export async function recomputeDimensions(runId: string) {
  const r = await fetch(`/history/runs/${runId}/recompute-dimensions`, { method: 'POST' });
  if (!r.ok) throw new Error(`recomputeDimensions failed: ${r.status}`);
  return r.json();
}
