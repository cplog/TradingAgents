import { useAutoAnimate } from "@formkit/auto-animate/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Pressable } from "../components/Pressable";
import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import {
  fetchConfig,
  fetchHealth,
  fetchHistoryRun,
  fetchProviderModels,
  filterAnalystsForBackend,
  mergeSupportedAnalystIds,
  getJob,
  getJobDimensions,
  openJobEvents,
  resumeJob,
  submitAnalyze,
  type HistoryRunDetail,
  type JobResultPayload,
  type JobStatus,
  type ProviderModel,
} from "../api";
import { DimensionsPanel } from "../components/dimensions/DimensionsPanel";
import type { DimensionsCommentary, StockDimensions } from "../dimensions-types";
import { orderedReportSectionKeys, prepareReportMarkdown } from "../utils/reportMarkdown";

const PROVIDERS = [
  "openai",
  "google",
  "anthropic",
  "deepseek",
  "openrouter",
  "moonshot",
  "xai",
  "qwen",
  "glm",
  "minimax",
  "ollama-local",
  "ollama-remote",
] as const;

const ANALYST_OPTIONS = [
  { id: "market", label: "Market" },
  { id: "social", label: "Social Media" },
  { id: "news", label: "News" },
  { id: "fundamentals", label: "Fundamentals" },
  { id: "hot_money", label: "Hot Money" },
  { id: "policy", label: "Policy" },
  { id: "lockup", label: "Lockup" },
  { id: "kronos", label: "Kronos forecast" },
] as const;

const REPORT_FORMATS = ["markdown", "json", "structured"] as const;
const DISCOVERABLE_PROVIDERS = new Set(["ollama-local", "ollama-remote", "openrouter"]);

const MODEL_PRESETS: Record<string, { deep: string; quick: string }> = {
  openai: { deep: "gpt-5.5", quick: "gpt-5.4-mini" },
  google: { deep: "gemini-3.1-pro-preview", quick: "gemini-3-flash-preview" },
  anthropic: { deep: "claude-opus-4-7", quick: "claude-sonnet-4-6" },
  deepseek: { deep: "deepseek-v4-pro", quick: "deepseek-v4-flash" },
  openrouter: { deep: "openrouter/free", quick: "openrouter/free" },
  moonshot: { deep: "moonshot-v1-8k", quick: "moonshot-v1-8k" },
  xai: { deep: "grok-4.20-reasoning", quick: "grok-4.20-non-reasoning" },
  qwen: { deep: "qwen3.6-plus", quick: "qwen3.6-flash" },
  glm: { deep: "glm-5.1", quick: "glm-5-turbo" },
  minimax: { deep: "MiniMax-M2.7", quick: "MiniMax-M2.7-highspeed" },
  ollama: { deep: "glm-4.7-flash:latest", quick: "qwen3:latest" },
  "ollama-local": { deep: "glm-4.7-flash:latest", quick: "qwen3:latest" },
  "ollama-remote": { deep: "glm-4.7-flash:latest", quick: "qwen3:latest" },
};

function slugifyHeading(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\u00C0-\u024f]+/gi, "-")
    .replace(/^-+|-+$/g, "");
}

function textFromChildren(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textFromChildren).join("");
  if (node && typeof node === "object" && "props" in node) {
    const p = (node as { props?: { children?: ReactNode } }).props;
    if (p?.children !== undefined) return textFromChildren(p.children);
  }
  return "";
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

/** Rough complexity hint from analyst count and debate rounds. */
function complexityHint(analysts: number, debate: number, risk: number): string {
  const parts: string[] = [];
  if (analysts >= 4 && debate >= 2) parts.push("full pipeline + heavier debate");
  else if (debate >= 2 || risk >= 2) parts.push("extra debate rounds");
  else parts.push("standard depth");
  return parts[0] ?? "";
}

/** Hydrate dashboard job state from a persisted History run (worker TTL expired). */
function historyRunToJobStatus(detail: HistoryRunDetail): JobStatus {
  const completedAt = detail.completed_at ?? new Date().toISOString();
  const result: JobResultPayload = {
    ticker: detail.ticker,
    date: detail.date,
    rating: detail.rating,
    confidence: detail.confidence,
    reports: detail.reports ?? {},
    structured: detail.structured ?? null,
    artifacts_path: detail.artifacts_path ?? null,
    completed_at: completedAt,
    dimensions: detail.dimensions ?? null,
    dimensions_commentary: detail.dimensions_commentary ?? null,
    dimensions_error: detail.dimensions_error ?? null,
    dimensions_in_graph: detail.dimensions_in_graph ?? null,
  };
  return {
    job_id: detail.job_id || detail.run_id,
    status: "completed",
    created_at: detail.created_at ?? completedAt,
    ticker: detail.ticker,
    date: detail.date,
    result,
    error: null,
    progress_events: [],
    batch_id: detail.batch_id ?? null,
  };
}

type PipelineMode = "idle" | "queued" | "pipeline" | "finalize" | "done" | "failed";

function inferPipelineMode(job: JobStatus | null, events: { message: string }[]): PipelineMode {
  if (!job) return "idle";
  if (job.status === "failed") return "failed";
  if (job.status === "completed") return "done";
  if (job.status === "queued") return "queued";
  const tail = [...events].reverse();
  for (const e of tail) {
    if (e.message.includes("Building report")) return "finalize";
  }
  if (job.status === "running") return "pipeline";
  return "idle";
}

function extractToc(md: string): { level: 2 | 3; text: string; id: string }[] {
  const out: { level: 2 | 3; text: string; id: string }[] = [];
  const seen = new Map<string, number>();
  for (const line of md.split("\n")) {
    const m = /^(#{2,3})\s+(.+)$/.exec(line.trim());
    if (!m) continue;
    const level = m[1].length as 2 | 3;
    const raw = m[2].trim();
    let id = slugifyHeading(raw);
    const n = seen.get(id) ?? 0;
    seen.set(id, n + 1);
    if (n > 0) id = `${id}-${n}`;
    out.push({ level, text: raw, id });
  }
  return out;
}

type DecisionSummary = {
  actionNow: "Buy now" | "Watchlist" | "Avoid for now";
  confidencePct: number | null;
  confidenceLabel: string;
  fomoLabel: "Low" | "Medium" | "High";
  whyNow: string[];
  invalidation: string;
  horizon: string;
};

function cleanLine(raw: string): string {
  return raw
    .replace(/\*\*/g, "")
    .replace(/^[-*]\s+/, "")
    .replace(/^#+\s+/, "")
    .replace(/\s+/g, " ")
    .trim();
}

function firstMeaningfulLines(text: string, limit = 3): string[] {
  const out: string[] = [];
  for (const line of text.split("\n")) {
    const cleaned = cleanLine(line);
    if (!cleaned) continue;
    if (cleaned.length < 28) continue;
    if (/^(rating|executive summary|investment thesis|final transaction proposal)/i.test(cleaned)) {
      continue;
    }
    if (out.includes(cleaned)) continue;
    out.push(cleaned);
    if (out.length >= limit) break;
  }
  return out;
}

function deriveDecisionSummary(
  reports: Record<string, string> | undefined,
  rating: string | null | undefined,
  confidence: number | null | undefined
): DecisionSummary {
  const r = (rating || "").toLowerCase();
  const actionNow: DecisionSummary["actionNow"] =
    r.includes("buy") || r.includes("overweight")
      ? "Buy now"
      : r.includes("sell") || r.includes("underweight")
        ? "Avoid for now"
        : "Watchlist";

  const confidencePct =
    confidence != null && Number.isFinite(confidence)
      ? Math.max(0, Math.min(100, Math.round(confidence * 100)))
      : null;
  const confidenceLabel =
    confidencePct == null
      ? "Not enough signal"
      : confidencePct >= 75
        ? "High conviction"
        : confidencePct >= 55
          ? "Balanced conviction"
          : "Low conviction";

  const socialText = (reports?.social || "").toLowerCase();
  const newsText = (reports?.news || "").toLowerCase();
  const hypeTerms = ["hype", "mania", "fomo", "euphoric", "parabolic", "squeeze"];
  const hypeHits = hypeTerms.reduce(
    (count, term) => count + (socialText.includes(term) || newsText.includes(term) ? 1 : 0),
    0
  );
  const fomoLabel: DecisionSummary["fomoLabel"] =
    hypeHits >= 2 || (actionNow === "Buy now" && (confidencePct ?? 0) < 60)
      ? "High"
      : hypeHits >= 1
        ? "Medium"
        : "Low";

  const whyNowSource =
    reports?.portfolio_decision || reports?.research_plan || reports?.market || "";
  const whyNow = firstMeaningfulLines(whyNowSource, 3);

  const traderPlan = reports?.trader_plan || "";
  const stopLossLine = traderPlan
    .split("\n")
    .map(cleanLine)
    .find((line) => /^stop loss:/i.test(line));
  const invalidation = stopLossLine
    ? stopLossLine.replace(/^stop loss:\s*/i, "")
    : "If thesis evidence weakens across fundamentals or trend confirmation, step back.";

  const pmText = reports?.portfolio_decision || "";
  const horizonMatch = pmText.match(/\*\*Time Horizon\*\*:\s*([^\n]+)/i);
  const horizon = horizonMatch?.[1]?.trim() || "3-6 months";

  return { actionNow, confidencePct, confidenceLabel, fomoLabel, whyNow, invalidation, horizon };
}

/** Map GET /config (already merged TRADINGAGENTS_* / .env on server) into form state. */
function hydrateFromServerConfig(
  cfg: Record<string, unknown>,
  setters: {
    setProvider: (v: string) => void;
    setDeepModel: (v: string) => void;
    setQuickModel: (v: string) => void;
    setDebate: (v: number) => void;
    setRiskRounds: (v: number) => void;
    setBackendUrl: (v: string) => void;
    setOutputLanguage: (v: string) => void;
    setOpenrouterFreeOnly: (v: boolean) => void;
    setTemperature: (v: number) => void;
    setApplyTemperature: (v: boolean) => void;
  }
) {
  const s = setters;
  if (typeof cfg.llm_provider === "string") {
    s.setProvider(cfg.llm_provider === "ollama" ? "ollama-local" : cfg.llm_provider);
  }
  if (typeof cfg.deep_think_llm === "string") s.setDeepModel(cfg.deep_think_llm);
  if (typeof cfg.quick_think_llm === "string") s.setQuickModel(cfg.quick_think_llm);
  if (typeof cfg.max_debate_rounds === "number") s.setDebate(cfg.max_debate_rounds);
  if (typeof cfg.max_risk_discuss_rounds === "number") s.setRiskRounds(cfg.max_risk_discuss_rounds);
  if (cfg.backend_url === null || cfg.backend_url === undefined) s.setBackendUrl("");
  else if (typeof cfg.backend_url === "string") s.setBackendUrl(cfg.backend_url);
  if (typeof cfg.output_language === "string") s.setOutputLanguage(cfg.output_language);
  if (typeof cfg.openrouter_free_only === "boolean") s.setOpenrouterFreeOnly(cfg.openrouter_free_only);
  if (typeof cfg.llm_temperature === "number" && !Number.isNaN(cfg.llm_temperature)) {
    s.setTemperature(cfg.llm_temperature);
    s.setApplyTemperature(true);
  }
}

export function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tickerFromQs = searchParams.get("ticker")?.trim() ?? "";
  const jobFromQs = searchParams.get("job")?.trim() ?? "";
  const [ticker, setTicker] = useState(() => tickerFromQs || "AAPL");
  const [date, setDate] = useState("");
  const [provider, setProvider] = useState<string>("openai");
  const [deepModel, setDeepModel] = useState("gpt-5.4");
  const [quickModel, setQuickModel] = useState("gpt-5.4-mini");
  const [backendUrl, setBackendUrl] = useState("");
  const [outputLanguage, setOutputLanguage] = useState("English");
  const [openrouterFreeOnly, setOpenrouterFreeOnly] = useState(false);
  const [temperature, setTemperature] = useState(0.7);
  const [applyTemperature, setApplyTemperature] = useState(false);
  const [debate, setDebate] = useState(1);
  const [riskRounds, setRiskRounds] = useState(1);
  const [selectedAnalysts, setSelectedAnalysts] = useState<string[]>(() =>
    ANALYST_OPTIONS.map((a) => a.id)
  );
  /** undefined = health not loaded yet; null = legacy payload (restrict extras); array = explicit allow-list */
  const [apiSupportedAnalystIds, setApiSupportedAnalystIds] = useState<string[] | null | undefined>(
    undefined
  );
  const [reportFormat, setReportFormat] = useState<string>("markdown");
  const [configHint, setConfigHint] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [logOpen, setLogOpen] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [events, setEvents] = useState<{ ts: string; stage: string; message: string }[]>([]);
  const [providerModels, setProviderModels] = useState<ProviderModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [modelsSource, setModelsSource] = useState<string | null>(null);
  const [modelsRefreshedAt, setModelsRefreshedAt] = useState<string | null>(null);
  const [deepCustomMode, setDeepCustomMode] = useState(false);
  const [quickCustomMode, setQuickCustomMode] = useState(false);
  const [jobNotice, setJobNotice] = useState<string | null>(null);
  const activeJobIdRef = useRef<string | null>(null);
  const [eventsLogRef] = useAutoAnimate();
  const esRef = useRef<EventSource | null>(null);
  const providerPreset = MODEL_PRESETS[provider] ?? MODEL_PRESETS.openai;
  const [dimensions, setDimensions] = useState<StockDimensions | null>(null);
  const [dimensionsCommentary, setDimensionsCommentary] = useState<DimensionsCommentary | null>(null);
  const [dimensionsError, setDimensionsError] = useState<string | null>(null);
  const [dimensionsCommentaryError, setDimensionsCommentaryError] = useState<string | null>(null);
  const [analysisTab, setAnalysisTab] = useState<"study" | "reports">("reports");
  const analysisInitializedFor = useRef<string | null>(null);

  useEffect(() => {
    if (tickerFromQs) setTicker(tickerFromQs);
  }, [tickerFromQs]);

  useEffect(() => {
    let cancelled = false;
    void Promise.allSettled([fetchHealth(), fetchConfig()]).then((results) => {
      if (cancelled) return;
      const h = results[0].status === "fulfilled" ? results[0].value : null;
      const cfg =
        results[1].status === "fulfilled" && results[1].value && typeof results[1].value === "object"
          ? (results[1].value as Record<string, unknown>)
          : null;
      setApiSupportedAnalystIds(mergeSupportedAnalystIds(h, cfg));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const tabFromQs = searchParams.get("tab");
  useEffect(() => {
    if (tabFromQs === "study" || tabFromQs === "reports") {
      setAnalysisTab(tabFromQs);
    }
  }, [tabFromQs]);

  const clearStaleJob = useCallback((message: string) => {
    const store = globalThis.localStorage;
    if (store && typeof store.removeItem === "function") {
      store.removeItem("ta:lastJobId");
    }
    activeJobIdRef.current = null;
    esRef.current?.close();
    setJobId(null);
    setJob(null);
    setEvents([]);
    setJobNotice(message);
  }, []);

  function handleProviderChange(nextProvider: string) {
    setProvider(nextProvider);
    setDeepCustomMode(false);
    setQuickCustomMode(false);
    const preset = MODEL_PRESETS[nextProvider];
    if (!preset) return;
    setDeepModel(preset.deep);
    setQuickModel(preset.quick);
    // OpenRouter is the only provider where free-only flag matters.
    if (nextProvider !== "openrouter") {
      setOpenrouterFreeOnly(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    const stripJobFromUrl = () => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.delete("job");
          next.delete("tab");
          return next;
        },
        { replace: true },
      );
    };

    async function restoreFromQuery(id: string) {
      const nowIso = new Date().toISOString();
      activeJobIdRef.current = id;
      setJobId(id);
      setJobNotice(null);
      setJob({
        job_id: id,
        status: "running",
        created_at: nowIso,
        ticker: null,
        date: null,
        result: null,
        error: null,
        progress_events: [
          {
            ts: nowIso,
            stage: "running",
            message: "Loading job from link…",
          },
        ],
        batch_id: null,
      });
      setEvents([
        {
          ts: nowIso,
          stage: "running",
          message: "Loading job from link…",
        },
      ]);
      try {
        const j = await getJob(id);
        if (cancelled || activeJobIdRef.current !== id) return;
        setJob(j);
        if (j.progress_events?.length) setEvents(j.progress_events);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.startsWith("404:")) {
          try {
            const persisted = await fetchHistoryRun(id);
            if (cancelled || activeJobIdRef.current !== id) return;
            setJob(historyRunToJobStatus(persisted));
            setJobNotice(
              "Loaded persisted run from History (live worker queue no longer has this job id).",
            );
            return;
          } catch {
            stripJobFromUrl();
            clearStaleJob(
              "Job not found (expired from the worker queue or invalid id). Open History for saved runs.",
            );
            return;
          }
        }
        setJobNotice(msg);
      }
    }

    async function restoreFromStorage(saved: string) {
      const nowIso = new Date().toISOString();
      activeJobIdRef.current = saved;
      setJobId(saved);
      setJob({
        job_id: saved,
        status: "running",
        created_at: nowIso,
        ticker: null,
        date: null,
        result: null,
        error: null,
        progress_events: [
          {
            ts: nowIso,
            stage: "running",
            message: "Restoring live job after refresh…",
          },
        ],
        batch_id: null,
      });
      setEvents([
        {
          ts: nowIso,
          stage: "running",
          message: "Restoring live job after refresh…",
        },
      ]);
      try {
        const j = await getJob(saved);
        if (cancelled || activeJobIdRef.current !== saved) return;
        if (j.status === "completed" || j.status === "failed" || j.status === "cancelled") {
          clearStaleJob(
            "Previous job is already finished. Start a new analysis here, or open History for past reports.",
          );
          return;
        }
        setJob(j);
        if (j.progress_events?.length) setEvents(j.progress_events);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.startsWith("404:")) {
          clearStaleJob(
            "Previous live job no longer exists (API restart/TTL). Use History for persisted runs or start a new analysis.",
          );
          return;
        }
        setJobNotice("Reconnecting to live job…");
      }
    }

    void (async () => {
      if (jobFromQs) {
        await restoreFromQuery(jobFromQs);
        return;
      }
      const store = globalThis.localStorage;
      if (!store || typeof store.getItem !== "function") return;
      const saved = store.getItem("ta:lastJobId");
      if (!saved) return;
      await restoreFromStorage(saved);
    })();

    return () => {
      cancelled = true;
    };
  }, [jobFromQs, clearStaleJob, setSearchParams]);
  const headingCursorRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    void fetchConfig()
      .then((cfg) => {
        if (cancelled) return;
        hydrateFromServerConfig(cfg, {
          setProvider,
          setDeepModel,
          setQuickModel,
          setDebate,
          setRiskRounds,
          setBackendUrl,
          setOutputLanguage,
          setOpenrouterFreeOnly,
          setTemperature,
          setApplyTemperature,
        });
        setConfigHint("Form filled from server config (TRADINGAGENTS_* / .env via GET /config).");
      })
      .catch(() => {
        if (!cancelled) {
          setConfigHint(
            "Could not load /config (is the API running on :8000 with Vite proxy?). Using local placeholders."
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const modelDiscoveryBackendUrl = useMemo(() => {
    const candidate = backendUrl.trim();
    if (!candidate) return undefined;
    if (provider.startsWith("ollama")) {
      // Avoid using stale OpenRouter backend URL for Ollama model discovery.
      if (candidate.includes("openrouter.ai")) return undefined;
      return candidate;
    }
    if (provider === "openrouter") {
      // Avoid using stale Ollama endpoint for OpenRouter model discovery.
      if (candidate.includes("/api/tags") || candidate.includes(":11434")) return undefined;
      return candidate;
    }
    return candidate;
  }, [provider, backendUrl]);

  const refreshProviderModels = useCallback(() => {
    if (!DISCOVERABLE_PROVIDERS.has(provider)) {
      setProviderModels([]);
      setModelsError(null);
      setModelsSource(null);
      setModelsRefreshedAt(null);
      setModelsLoading(false);
      return;
    }
    let cancelled = false;
    setModelsLoading(true);
    setModelsError(null);
    void fetchProviderModels(provider, modelDiscoveryBackendUrl)
      .then((payload) => {
        if (cancelled) return;
        const discovered = Array.isArray(payload.models) ? payload.models : [];
        setProviderModels(discovered);
        setModelsSource(payload.source || null);
        setModelsRefreshedAt(new Date().toISOString());
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setProviderModels([]);
        setModelsError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setModelsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [provider, modelDiscoveryBackendUrl]);

  useEffect(() => {
    const cleanup = refreshProviderModels();
    return cleanup;
  }, [refreshProviderModels]);

  const poll = useCallback(async (id: string) => {
    try {
      const j = await getJob(id);
      if (activeJobIdRef.current !== id) return;
      setJobNotice(null);
      setJob(j);
      if (j.progress_events?.length) setEvents(j.progress_events);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.startsWith("404:")) {
        if (activeJobIdRef.current !== id) return;
        try {
          const persisted = await fetchHistoryRun(id);
          if (activeJobIdRef.current !== id) return;
          setJob(historyRunToJobStatus(persisted));
          setJobNotice(
            "Loaded persisted run from History (live worker queue no longer has this job id).",
          );
          return;
        } catch {
          clearStaleJob(
            "Live polling stopped because this job is no longer in memory. Open History to compare persisted runs.",
          );
        }
      }
    }
  }, [clearStaleJob]);

  useEffect(() => {
    if (!jobId) return;
    if (job?.status && job.status !== "queued" && job.status !== "running") {
      return;
    }
    poll(jobId);
    const t = setInterval(() => poll(jobId), 4000);
    return () => clearInterval(t);
  }, [jobId, job?.status, poll]);

  useEffect(() => {
    if (!jobId) return;
    if (
      job?.status &&
      job.status !== "queued" &&
      job.status !== "running"
    ) {
      esRef.current?.close();
      esRef.current = null;
      return;
    }
    esRef.current?.close();
    const es = openJobEvents(jobId);
    esRef.current = es;
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === "terminal") {
          poll(jobId);
          es.close();
        } else if (data.message) {
          setEvents((prev) => [...prev, data]);
        }
      } catch {
        /* ignore */
      }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [jobId, job?.status, poll]);

  const jobActive =
    job?.status === "queued" || job?.status === "running" || submitting;

  useEffect(() => {
    if (job?.status === "running" || job?.status === "queued") {
      setLogOpen(true);
    }
  }, [job?.status]);

  const [elapsedSec, setElapsedSec] = useState(0);
  useEffect(() => {
    const active = job?.status === "running" || job?.status === "queued";
    if (!active || !job?.created_at) {
      setElapsedSec(0);
      return;
    }
    const tick = () => {
      setElapsedSec(
        Math.max(0, Math.floor((Date.now() - new Date(job.created_at).getTime()) / 1000))
      );
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [job?.status, job?.created_at]);

  async function resumeAnalysis() {
    if (!jobId) return;
    setSubmitting(true);
    setJobNotice(null);
    try {
      const r = await resumeJob(jobId);
      setJobNotice(r.message);
      activeJobIdRef.current = jobId;
      await poll(jobId);
    } finally {
      setSubmitting(false);
    }
  }

  async function runAnalysis() {
    setSubmitting(true);
    setJobNotice(null);
    setEvents([]);
    setJob(null);
    const overrides: Record<string, unknown> = {
      llm_provider: provider,
      deep_think_llm: deepModel,
      quick_think_llm: quickModel,
      max_debate_rounds: debate,
      max_risk_discuss_rounds: riskRounds,
      output_language: outputLanguage,
      openrouter_free_only: openrouterFreeOnly,
    };
    if (applyTemperature) overrides.llm_temperature = temperature;
    const trimmedBackend = backendUrl.trim();
    const providerIsOllama = provider.startsWith("ollama");
    if (providerIsOllama) {
      // Important: do not inherit server-level OpenRouter backend_url when user switches
      // to Ollama providers in the UI. Force null unless a non-OpenRouter URL is given.
      if (trimmedBackend && !trimmedBackend.includes("openrouter.ai")) {
        overrides.backend_url = trimmedBackend;
      } else {
        overrides.backend_url = null;
      }
    } else if (trimmedBackend) {
      overrides.backend_url = trimmedBackend;
    }
    try {
      const { analysts: analystsPayload, dropped } = filterAnalystsForBackend(
        selectedAnalysts,
        apiSupportedAnalystIds
      );
      if (dropped.length) {
        setJobNotice(
          `Unsupported analyst(s) on this API — omitted from request: ${dropped.join(", ")}. ` +
            `Run the API from this repo (\`pip install -e .\`, then \`uvicorn api.main:app --port 8000\`) so all focus areas are accepted.`
        );
      }
      const r = await submitAnalyze({
        ticker: ticker.trim(),
        date: date || undefined,
        config_overrides: overrides,
        analysts: analystsPayload,
        report_format: reportFormat as "markdown" | "json" | "structured",
      });
      const store = globalThis.localStorage;
      if (store && typeof store.setItem === "function") {
        store.setItem("ta:lastJobId", r.job_id);
      }
      activeJobIdRef.current = r.job_id;
      setJobId(r.job_id);
      await poll(r.job_id);
    } finally {
      setSubmitting(false);
    }
  }

  useEffect(() => {
    if (!jobId || job?.status !== "completed" || !job?.result) {
      return;
    }
    const doneKey = `${jobId}:${String(job.result.completed_at)}`;
    const r = job.result as JobResultPayload;

    if ("dimensions" in r || "dimensions_error" in r) {
      setDimensions(r.dimensions ?? null);
      setDimensionsCommentary(r.dimensions_commentary ?? null);
      setDimensionsError(r.dimensions_error && !r.dimensions ? r.dimensions_error : null);
      setDimensionsCommentaryError(
        r.dimensions_error && r.dimensions ? r.dimensions_error : null,
      );
      if (analysisInitializedFor.current !== doneKey) {
        analysisInitializedFor.current = doneKey;
        const openStudy = Boolean(r.dimensions || (r.dimensions_error && !r.dimensions));
        setAnalysisTab(openStudy ? "study" : "reports");
      }
      return;
    }

    let cancelled = false;
    setDimensionsError(null);
    setDimensionsCommentaryError(null);
    void getJobDimensions(jobId)
      .then((b) => {
        if (cancelled) return;
        setDimensions(b.dimensions);
        setDimensionsCommentary(b.commentary);
        setDimensionsError(b.error && !b.dimensions ? b.error : null);
        setDimensionsCommentaryError(b.error && b.dimensions ? b.error : null);
        if (analysisInitializedFor.current !== doneKey) {
          analysisInitializedFor.current = doneKey;
          setAnalysisTab(b.dimensions || b.error ? "study" : "reports");
        }
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setDimensions(null);
        setDimensionsCommentary(null);
        setDimensionsError(e instanceof Error ? e.message : String(e));
        setDimensionsCommentaryError(null);
        if (analysisInitializedFor.current !== doneKey) {
          analysisInitializedFor.current = doneKey;
          setAnalysisTab("reports");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, job?.status, job?.result]);

  useEffect(() => {
    if (job?.status === "queued" || job?.status === "running") {
      setDimensions(null);
      setDimensionsCommentary(null);
      setDimensionsError(null);
      setDimensionsCommentaryError(null);
      analysisInitializedFor.current = null;
    }
  }, [job?.status]);

  const mdReport = useMemo(() => {
    const reps = job?.result?.reports;
    if (!reps || typeof reps !== "object") return "";
    const keys = orderedReportSectionKeys(reps);
    return keys
      .map((k) => prepareReportMarkdown(k, reps[k] ?? ""))
      .filter(Boolean)
      .join("\n\n---\n\n");
  }, [job?.result?.reports]);

  const showDimensionalStudy = Boolean(
    job?.status === "completed" && (dimensions || dimensionsError),
  );
  const showAgentReports = Boolean(mdReport);
  const showAnalysisTabs = showDimensionalStudy && showAgentReports;

  const tocItems = useMemo(() => extractToc(mdReport), [mdReport]);
  const tocLevel2 = useMemo(() => tocItems.filter((t) => t.level === 2), [tocItems]);
  const pipelineMode = useMemo(() => inferPipelineMode(job, events), [job, events]);

  const completedSeconds = useMemo(() => {
    if (!job?.created_at || !job?.result?.completed_at) return null;
    const start = new Date(job.created_at).getTime();
    const end = new Date(job.result.completed_at).getTime();
    const d = Math.floor((end - start) / 1000);
    return Number.isFinite(d) && d >= 0 ? d : null;
  }, [job?.created_at, job?.result?.completed_at]);

  const hintLine = complexityHint(selectedAnalysts.length, debate, riskRounds);
  const visibleProviderModels = useMemo(() => {
    if (provider !== "openrouter") return providerModels;
    if (!openrouterFreeOnly) return providerModels;
    return providerModels.filter((m) => Boolean(m.is_free));
  }, [provider, providerModels, openrouterFreeOnly]);
  const deepModelInOptions = visibleProviderModels.some((m) => m.id === deepModel);
  const quickModelInOptions = visibleProviderModels.some((m) => m.id === quickModel);
  useEffect(() => {
    if (!visibleProviderModels.length) return;
    if (!deepCustomMode && !deepModelInOptions) {
      setDeepModel(visibleProviderModels[0].id);
    }
    if (!quickCustomMode && !quickModelInOptions) {
      setQuickModel(visibleProviderModels[0].id);
    }
  }, [
    visibleProviderModels,
    deepCustomMode,
    quickCustomMode,
    deepModelInOptions,
    quickModelInOptions,
  ]);
  const decisionSummary = useMemo(
    () => deriveDecisionSummary(job?.result?.reports, job?.result?.rating, job?.result?.confidence),
    [job?.result?.reports, job?.result?.rating, job?.result?.confidence]
  );

  const activePipelineStep = useMemo(() => {
    switch (pipelineMode) {
      case "queued":
        return 0;
      case "pipeline":
        return 1;
      case "finalize":
        return 2;
      case "done":
        return 3;
      case "failed":
        return 1;
      default:
        return -1;
    }
  }, [pipelineMode]);

  const pipelineLabels = ["Queued", "Pipeline", "Report", "Done"];

  headingCursorRef.current = 0;
  const markdownComponents = useMemo((): Components => ({
    table: ({ children, ...rest }) => (
      <div className="markdown-table-wrap">
        <table {...rest}>{children}</table>
      </div>
    ),
    h2: ({ children }) => {
      const pos = headingCursorRef.current;
      const item = tocItems[pos];
      let id = slugifyHeading(textFromChildren(children));
      if (item?.level === 2) {
        id = item.id;
        headingCursorRef.current += 1;
      }
      return (
        <h2
          id={id}
          style={{
            scrollMarginTop: "var(--spacing-24)",
            fontSize: "var(--text-heading)",
            marginTop: "var(--spacing-24)",
            marginBottom: "var(--spacing-8)",
            color: "var(--color-slate-text)",
          }}
        >
          {children}
        </h2>
      );
    },
    h3: ({ children }) => {
      const pos = headingCursorRef.current;
      const item = tocItems[pos];
      let id = slugifyHeading(textFromChildren(children));
      if (item?.level === 3) {
        id = item.id;
        headingCursorRef.current += 1;
      }
      return (
        <h3
          id={id}
          style={{
            scrollMarginTop: "var(--spacing-24)",
            fontSize: "var(--text-heading-sm)",
            marginTop: "var(--spacing-16)",
            marginBottom: "var(--spacing-8)",
            color: "var(--color-slate-text)",
          }}
        >
          {children}
        </h3>
      );
    },
  }), [tocItems]);

  function pipelineDotClass(i: number): string {
    if (pipelineMode === "failed" && i === 1) return "pipeline-dot pipeline-dot--error";
    const done = job?.status === "completed" || pipelineMode === "done";
    if (done) return "pipeline-dot pipeline-dot--done";
    if (activePipelineStep < 0) return "pipeline-dot pipeline-dot--todo";
    if (i < activePipelineStep) return "pipeline-dot pipeline-dot--done";
    if (i === activePipelineStep) return "pipeline-dot pipeline-dot--active";
    return "pipeline-dot pipeline-dot--todo";
  }

  return (
    <div
      className="dashboard-page"
      style={{ display: "grid", gap: "var(--spacing-24)" }}
    >
      <header>
        <h1 style={{ fontSize: "var(--text-heading-lg)", margin: "0 0 8px" }}>
          Main analysis
        </h1>
        <p style={{ margin: 0, color: "var(--color-ash-gray)" }}>
          Single-stock agentic workflow with live progress and markdown output. Outputs are research
          artifacts, not financial advice.
        </p>
        {configHint && (
          <p
            style={{
              margin: "var(--spacing-12) 0 0",
              fontSize: "var(--text-caption)",
              color: "var(--color-steel-gray)",
            }}
          >
            {configHint}
          </p>
        )}
        {jobNotice && (
          <p
            style={{
              margin: "var(--spacing-12) 0 0",
              fontSize: "var(--text-caption)",
              color: "#92400e",
            }}
          >
            {jobNotice}
          </p>
        )}
      </header>

      <section className="dashboard-main-grid">
        <div
          className="dashboard-setup-card"
          style={{
            background: "var(--surface-cloud-white)",
            padding: "var(--card-padding)",
            borderRadius: "var(--radius-cards)",
            boxShadow: "var(--shadow-subtle)",
            border: "1px solid var(--color-stone-border)",
          }}
        >
          <h2 style={{ marginTop: 0 }}>Setup</h2>
          <p style={{ margin: "0 0 var(--spacing-16)", fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>
            Essentials cover most runs. Open Advanced for routing, sampling, and debate depth.
          </p>

          <fieldset style={{ border: "none", margin: 0, padding: 0 }}>
            <legend style={{ fontWeight: 600, marginBottom: "var(--spacing-12)", fontSize: "var(--text-caption)" }}>
              Essentials
            </legend>
            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
                LLM provider
              </span>
              <select
                value={provider}
                onChange={(e) => handleProviderChange(e.target.value)}
                disabled={jobActive}
                style={{ width: "100%", padding: 8, borderRadius: "var(--radius-inputs)" }}
              >
                {PROVIDERS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
                Deep model
              </span>
              {visibleProviderModels.length > 0 && !deepCustomMode ? (
                <select
                  value={deepModelInOptions ? deepModel : ""}
                  onChange={(e) => {
                    const next = e.target.value;
                    if (next === "__custom__") {
                      setDeepCustomMode(true);
                      return;
                    }
                    setDeepModel(next);
                  }}
                  disabled={jobActive || modelsLoading}
                  style={{ width: "100%", padding: 8, borderRadius: "var(--radius-inputs)" }}
                >
                  {!deepModelInOptions && <option value="">Select a model…</option>}
                  {visibleProviderModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.loaded ? `${m.label} (loaded)` : m.label}
                    </option>
                  ))}
                  <option value="__custom__">Custom model ID…</option>
                </select>
              ) : (
                <input
                  value={deepModel}
                  onChange={(e) => setDeepModel(e.target.value)}
                  disabled={jobActive}
                  style={{ width: "100%", padding: 8 }}
                />
              )}
              {deepCustomMode && (
                <button
                  type="button"
                  onClick={() => setDeepCustomMode(false)}
                  style={{
                    marginTop: 6,
                    fontSize: 11,
                    border: "1px solid var(--color-stone-border)",
                    background: "transparent",
                    borderRadius: "var(--radius-inputs)",
                    padding: "2px 8px",
                    cursor: "pointer",
                  }}
                >
                  Back to discovered models
                </button>
              )}
              <span style={{ fontSize: 11, color: "var(--color-ash-gray)" }}>
                Suggested for {provider}: {providerPreset.deep}
              </span>
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
                Quick model
              </span>
              {visibleProviderModels.length > 0 && !quickCustomMode ? (
                <select
                  value={quickModelInOptions ? quickModel : ""}
                  onChange={(e) => {
                    const next = e.target.value;
                    if (next === "__custom__") {
                      setQuickCustomMode(true);
                      return;
                    }
                    setQuickModel(next);
                  }}
                  disabled={jobActive || modelsLoading}
                  style={{ width: "100%", padding: 8, borderRadius: "var(--radius-inputs)" }}
                >
                  {!quickModelInOptions && <option value="">Select a model…</option>}
                  {visibleProviderModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.loaded ? `${m.label} (loaded)` : m.label}
                    </option>
                  ))}
                  <option value="__custom__">Custom model ID…</option>
                </select>
              ) : (
                <input
                  value={quickModel}
                  onChange={(e) => setQuickModel(e.target.value)}
                  disabled={jobActive}
                  style={{ width: "100%", padding: 8 }}
                />
              )}
              {quickCustomMode && (
                <button
                  type="button"
                  onClick={() => setQuickCustomMode(false)}
                  style={{
                    marginTop: 6,
                    fontSize: 11,
                    border: "1px solid var(--color-stone-border)",
                    background: "transparent",
                    borderRadius: "var(--radius-inputs)",
                    padding: "2px 8px",
                    cursor: "pointer",
                  }}
                >
                  Back to discovered models
                </button>
              )}
              <span style={{ fontSize: 11, color: "var(--color-ash-gray)" }}>
                Suggested for {provider}: {providerPreset.quick}
              </span>
            </label>
            {DISCOVERABLE_PROVIDERS.has(provider) && (
              <div
                style={{
                  marginTop: -4,
                  marginBottom: 12,
                  fontSize: 11,
                  color: "var(--color-ash-gray)",
                  border: "1px solid var(--color-stone-border)",
                  background: "var(--surface-canvas-fog)",
                  borderRadius: "var(--radius-cards)",
                  padding: "10px 12px",
                  display: "grid",
                  gap: 8,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                  <span style={{ fontWeight: 600, color: "var(--color-slate-text)" }}>
                    Model Discovery ({provider})
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      void refreshProviderModels();
                    }}
                    disabled={jobActive || modelsLoading}
                    style={{
                      fontSize: 11,
                      border: "1px solid var(--color-stone-border)",
                      background: "var(--surface-cloud-white)",
                      borderRadius: "var(--radius-inputs)",
                      padding: "2px 8px",
                      cursor: jobActive || modelsLoading ? "not-allowed" : "pointer",
                    }}
                  >
                    {modelsLoading ? "Refreshing..." : "Refresh"}
                  </button>
                </div>
                {modelsLoading && <span>Checking available models...</span>}
                {!modelsLoading && modelsError && (
                  <span>
                    Could not query provider models ({modelsError}). Using manual/preset models. If this
                    just changed, restart API server once.
                  </span>
                )}
                {!modelsLoading && !modelsError && modelsSource && (
                  <span>
                    Found {visibleProviderModels.length} model(s) from{" "}
                    <span className="mono">{modelsSource}</span>
                    {modelsRefreshedAt ? ` - updated ${new Date(modelsRefreshedAt).toLocaleTimeString()}` : ""}
                  </span>
                )}
              </div>
            )}
            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
                Output language
              </span>
              <input
                value={outputLanguage}
                onChange={(e) => setOutputLanguage(e.target.value)}
                disabled={jobActive}
                style={{ width: "100%", padding: 8 }}
              />
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
                Focus area (analysts)
              </span>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {ANALYST_OPTIONS.map((a) => (
                  <label key={a.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14 }}>
                    <input
                      type="checkbox"
                      checked={selectedAnalysts.includes(a.id)}
                      disabled={jobActive}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedAnalysts((prev) => [...prev, a.id]);
                        } else {
                          setSelectedAnalysts((prev) => prev.filter((id) => id !== a.id));
                        }
                      }}
                    />
                    {a.label}
                  </label>
                ))}
              </div>
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
                Report format
              </span>
              <select
                value={reportFormat}
                onChange={(e) => setReportFormat(e.target.value)}
                disabled={jobActive}
                style={{ width: "100%", padding: 8, borderRadius: "var(--radius-inputs)" }}
              >
                {REPORT_FORMATS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </label>
          </fieldset>

          <details style={{ marginTop: "var(--spacing-16)" }}>
            <summary
              style={{
                cursor: "pointer",
                fontWeight: 600,
                fontSize: "var(--text-caption)",
                color: "var(--color-slate-text)",
                marginBottom: "var(--spacing-12)",
              }}
            >
              Advanced
            </summary>
            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
                LLM backend URL (optional override)
              </span>
              <input
                value={backendUrl}
                onChange={(e) => setBackendUrl(e.target.value)}
                placeholder="https://openrouter.ai/api/v1"
                disabled={jobActive}
                style={{ width: "100%", padding: 8 }}
                className="mono"
              />
              <span style={{ fontSize: 11, color: "var(--color-ash-gray)" }}>
                Leave blank for server default (e.g. from .env).
              </span>
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <input
                type="checkbox"
                checked={openrouterFreeOnly}
                disabled={jobActive}
                onChange={(e) => setOpenrouterFreeOnly(e.target.checked)}
              />
              <span style={{ fontSize: 14 }}>OpenRouter free models only</span>
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
                Temperature: {temperature.toFixed(2)}
              </span>
              <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <input
                  type="checkbox"
                  checked={applyTemperature}
                  disabled={jobActive}
                  onChange={(e) => setApplyTemperature(e.target.checked)}
                />
                <span style={{ fontSize: 13 }}>Send temperature on each run (otherwise model default)</span>
              </label>
              <input
                type="range"
                min={0}
                max={2}
                step={0.05}
                value={temperature}
                onChange={(e) => setTemperature(Number(e.target.value))}
                disabled={!applyTemperature || jobActive}
                style={{ width: "100%", opacity: applyTemperature ? 1 : 0.5 }}
              />
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
                Debate rounds
              </span>
              <input
                type="number"
                min={0}
                max={5}
                value={debate}
                disabled={jobActive}
                onChange={(e) => setDebate(Number(e.target.value))}
                style={{ width: "100%", padding: 8 }}
              />
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
                Risk rounds
              </span>
              <input
                type="number"
                min={0}
                max={5}
                value={riskRounds}
                disabled={jobActive}
                onChange={(e) => setRiskRounds(Number(e.target.value))}
                style={{ width: "100%", padding: 8 }}
              />
            </label>
          </details>
        </div>

        <div
          className="dashboard-run-card"
          style={{
            background: "var(--surface-cloud-white)",
            padding: "var(--card-padding)",
            borderRadius: "var(--radius-cards)",
            boxShadow: "var(--shadow-subtle)",
            border: "1px solid var(--color-stone-border)",
          }}
        >
          <h2 style={{ marginTop: 0 }}>Run</h2>
          <label style={{ display: "block", marginBottom: 12 }}>
            <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
              Ticker
            </span>
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              disabled={jobActive}
              style={{ width: "100%", padding: 8, marginTop: 4 }}
            />
          </label>
          <label style={{ display: "block", marginBottom: 12 }}>
            <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
              Date (YYYY-MM-DD, optional)
            </span>
            <input
              value={date}
              onChange={(e) => setDate(e.target.value)}
              placeholder="today"
              disabled={jobActive}
              style={{ width: "100%", padding: 8, marginTop: 4 }}
            />
          </label>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--spacing-8)",
              flexWrap: "wrap",
              marginBottom: "var(--spacing-12)",
              fontSize: "var(--text-caption)",
              color: "var(--color-ash-gray)",
            }}
          >
            <span className="mono">
              {provider} · {quickModel}
            </span>
            {hintLine && <span>· {hintLine}</span>}
          </div>

          <div className="pipeline-track" style={{ marginBottom: "var(--spacing-16)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 4 }}>
              {pipelineLabels.map((label, i) => (
                <div key={label} style={{ flex: 1, textAlign: "center", minWidth: 0 }}>
                  <div className={pipelineDotClass(i)} title={label} />
                  <div
                    style={{
                      fontSize: 10,
                      color: "var(--color-steel-gray)",
                      marginTop: 4,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {label}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <Pressable
            disabled={jobActive || apiSupportedAnalystIds === undefined}
            onClick={() => void runAnalysis().catch((e) => alert(String(e)))}
            style={{
              width: "100%",
              padding: "12px 16px",
              borderRadius: "var(--radius-buttons)",
              background:
                jobActive || apiSupportedAnalystIds === undefined
                  ? "var(--color-platinum-outline)"
                  : "var(--color-chartwell-blue)",
              color:
                jobActive || apiSupportedAnalystIds === undefined
                  ? "var(--color-steel-gray)"
                  : "white",
              border: "none",
              fontWeight: 600,
              cursor:
                jobActive || apiSupportedAnalystIds === undefined ? "not-allowed" : "pointer",
            }}
          >
            {apiSupportedAnalystIds === undefined
              ? "Checking API…"
              : submitting
                ? "Starting…"
                : jobActive
                  ? "Running…"
                  : "Start analysis"}
          </Pressable>

          {jobId && (
            <div style={{ marginTop: "var(--spacing-16)", fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>
              <div>
                Job <span className="mono">{jobId}</span> — <strong>{job?.status ?? "…"}</strong>
              </div>
              {(job?.status === "running" || job?.status === "queued") && (
                <div style={{ marginTop: 6 }}>
                  Elapsed: <span className="mono">{formatDuration(elapsedSec)}</span>
                  {" · "}
                  Heartbeat ~45s during long LLM calls
                </div>
              )}
              {job?.status === "completed" && completedSeconds != null && (
                <div style={{ marginTop: 6 }}>
                  Finished in <span className="mono">{formatDuration(completedSeconds)}</span>
                </div>
              )}
              <div style={{ marginTop: 8 }}>
                Share:{" "}
                <a
                  href={`/runs/${encodeURIComponent(jobId)}`}
                  style={{ color: "var(--color-chartwell-blue)" }}
                >
                  /runs/{jobId}
                </a>
                {" · "}
                <a
                  href={`/runs/${encodeURIComponent(jobId)}/results`}
                  style={{ color: "var(--color-chartwell-blue)" }}
                >
                  results tab
                </a>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="dashboard-log-section">
        <button
          type="button"
          onClick={() => setLogOpen(!logOpen)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            background: "var(--color-ghost-ink)",
            color: "var(--surface-cloud-white)",
            border: "none",
            padding: "10px 14px",
            borderRadius: "var(--radius-md)",
            cursor: "pointer",
            width: "100%",
            justifyContent: "space-between",
          }}
        >
          <span className="mono" style={{ fontWeight: 600 }}>
            Progress log {logOpen ? "▼" : "▶"}
          </span>
          <span style={{ fontSize: "var(--text-caption)", opacity: 0.85 }}>
            {jobActive ? "live" : "SSE + poll"}
          </span>
        </button>
        <p
          style={{
            margin: "6px 0 0",
            fontSize: 11,
            color: "var(--color-ash-gray)",
          }}
        >
          While <span className="mono">propagate()</span> runs, steps inside LangGraph are coarse-grained.
          Expect a heartbeat about every 45s during long provider calls.
        </p>
        {logOpen && (
          <pre
            className="mono dashboard-progress-log"
            style={{
              marginTop: 8,
              maxHeight: 320,
              overflow: "auto",
              background: "#1a1816",
              color: "#e7e5e4",
              padding: "var(--spacing-16)",
              borderRadius: "var(--radius-md)",
              fontSize: 13,
              lineHeight: 1.5,
              whiteSpace: "pre-wrap",
              overflowWrap: "anywhere",
              wordBreak: "break-word",
            }}
          >
            <div ref={eventsLogRef}>
              {events.length === 0 && jobActive && (
                <div style={{ color: "#94a3b8" }}>Waiting for first progress event…</div>
              )}
              {events.map((e, i) => (
                <div key={`${e.ts}-${i}`} className="dashboard-progress-log__entry">
                  <span style={{ color: "#94a3b8" }}>[{e.stage}]</span> {e.message}
                </div>
              ))}
            </div>
          </pre>
        )}
      </section>

      {job?.error && (
        <div
          style={{
            padding: "var(--spacing-16)",
            background: "#fef2f2",
            color: "#991b1b",
            borderRadius: "var(--radius-md)",
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: "var(--spacing-16)",
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div>{job.error}</div>
            {job.resumable && (
              <div style={{ marginTop: "var(--spacing-8)", color: "#7f1d1d", fontSize: "var(--text-caption)" }}>
                LangGraph checkpoint
                {job.last_graph_step != null ? ` at step ${job.last_graph_step}` : ""}
                {" "}— you can resume without restarting from the first analyst.
              </div>
            )}
          </div>
          <div style={{ display: "flex", flexShrink: 0, gap: "var(--spacing-8)" }}>
            {job.resumable && job.status === "failed" && (
              <button
                type="button"
                disabled={submitting}
                onClick={() => void resumeAnalysis()}
                style={{
                  padding: "6px 12px",
                  borderRadius: "var(--radius-buttons)",
                  border: "1px solid #fca5a5",
                  background: "#dc2626",
                  color: "white",
                  cursor: submitting ? "not-allowed" : "pointer",
                  fontSize: "var(--text-caption)",
                  fontWeight: 600,
                }}
              >
                Resume analysis
              </button>
            )}
            <button
              type="button"
              onClick={() => navigator.clipboard.writeText(job.error ?? "")}
              style={{
                padding: "6px 12px",
                borderRadius: "var(--radius-buttons)",
                border: "1px solid #fecaca",
                background: "white",
                color: "#991b1b",
                cursor: "pointer",
                fontSize: "var(--text-caption)",
              }}
            >
              Copy
            </button>
          </div>
        </div>
      )}

      {(showDimensionalStudy || showAgentReports) && (
        <div style={{ display: "grid", gap: "var(--spacing-16)" }}>
          {showAnalysisTabs && (
            <div
              role="tablist"
              aria-label="Analysis views"
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 8,
                padding: 6,
                background: "var(--surface-cloud-white)",
                borderRadius: "var(--radius-cards)",
                border: "1px solid var(--color-stone-border)",
                boxShadow: "var(--shadow-subtle)",
              }}
            >
              <button
                type="button"
                role="tab"
                aria-selected={analysisTab === "study"}
                onClick={() => setAnalysisTab("study")}
                style={{
                  padding: "10px 16px",
                  borderRadius: "var(--radius-buttons)",
                  border:
                    analysisTab === "study"
                      ? "1px solid var(--color-chartwell-blue)"
                      : "1px solid transparent",
                  background: analysisTab === "study" ? "var(--color-sky-tint)" : "transparent",
                  cursor: "pointer",
                  fontWeight: analysisTab === "study" ? 600 : 400,
                  color: "var(--color-slate-text)",
                }}
              >
                Dimensional study
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={analysisTab === "reports"}
                onClick={() => setAnalysisTab("reports")}
                style={{
                  padding: "10px 16px",
                  borderRadius: "var(--radius-buttons)",
                  border:
                    analysisTab === "reports"
                      ? "1px solid var(--color-chartwell-blue)"
                      : "1px solid transparent",
                  background: analysisTab === "reports" ? "var(--color-sky-tint)" : "transparent",
                  cursor: "pointer",
                  fontWeight: analysisTab === "reports" ? 600 : 400,
                  color: "var(--color-slate-text)",
                }}
              >
                Agent reports
              </button>
            </div>
          )}

          {showDimensionalStudy && (!showAnalysisTabs || analysisTab === "study") && (
            <section
              id="ta-dimensional-study"
              style={{
                background: "var(--surface-cloud-white)",
                padding: "var(--spacing-24)",
                borderRadius: "var(--radius-largecard)",
                boxShadow: "var(--shadow-md)",
                border: "1px solid var(--color-stone-border)",
              }}
            >
              {job?.result?.dimensions_in_graph === true && (
                <div
                  style={{
                    marginBottom: "var(--spacing-12)",
                    fontSize: "var(--text-caption)",
                    color: "#166534",
                    fontWeight: 500,
                  }}
                >
                  This run fed a dimensional snapshot into Trader and Portfolio Manager before the final rating.
                </div>
              )}
              {job?.result?.dimensions_in_graph === false && (
                <div
                  style={{
                    marginBottom: "var(--spacing-12)",
                    fontSize: "var(--text-caption)",
                    color: "var(--color-ash-gray)",
                  }}
                >
                  No in-graph snapshot on this run; scores below may come only from the post-pass.
                </div>
              )}
              <DimensionsPanel
                dimensions={dimensions}
                commentary={dimensionsCommentary}
                error={dimensionsError}
                commentaryError={dimensionsCommentaryError}
              />
            </section>
          )}

          {showAgentReports && (!showAnalysisTabs || analysisTab === "reports") && (
            <article
              style={{
                background: "var(--surface-cloud-white)",
                padding: "clamp(var(--spacing-24), 3vw, var(--spacing-32))",
                borderRadius: "var(--radius-largecard)",
                boxShadow: "var(--shadow-md)",
                border: "1px solid var(--color-stone-border)",
                display: "grid",
                gap: "var(--spacing-32)",
              }}
            >
              <header style={{ display: "grid", gap: "var(--spacing-8)" }}>
                <p
                  style={{
                    margin: 0,
                    fontSize: "var(--text-caption)",
                    fontWeight: 600,
                    letterSpacing: "0.02em",
                    textTransform: "uppercase",
                    color: "var(--color-steel-gray)",
                  }}
                >
                  Agent reports
                </p>
                <p style={{ margin: 0, fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>
                  Research artifacts only — not financial advice. Read full context in the sections below.
                </p>
              </header>

              <section
                style={{
                  display: "grid",
                  gap: "var(--spacing-16)",
                  paddingBottom: "var(--spacing-24)",
                  borderBottom: "1px solid var(--color-stone-border)",
                }}
              >
                <div
                  style={{
                    fontSize: "var(--text-heading)",
                    fontWeight: 600,
                    letterSpacing: "-0.02em",
                    lineHeight: 1.2,
                    color: "var(--color-slate-text)",
                  }}
                >
                  {job?.result?.rating ?? "—"}
                </div>
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "baseline",
                    gap: "var(--spacing-8) var(--spacing-16)",
                    fontSize: "var(--text-caption)",
                    color: "var(--color-steel-gray)",
                  }}
                >
                  <span className="mono" style={{ color: "var(--color-slate-text)", fontWeight: 600 }}>
                    {job?.result?.ticker ?? ticker}
                  </span>
                  {job?.result?.date && <span>As of {job.result.date}</span>}
                  {job?.result?.confidence != null && (
                    <span>
                      Confidence <span style={{ color: "var(--color-ash-gray)" }}>(heuristic)</span>:{" "}
                      {(job.result.confidence * 100).toFixed(0)}%
                    </span>
                  )}
                  {jobId && (
                    <a
                      href={`/jobs/${jobId}/report`}
                      className="mono"
                      style={{
                        marginLeft: "auto",
                        fontSize: "var(--text-caption)",
                        color: "var(--color-chartwell-blue)",
                        fontWeight: 500,
                      }}
                    >
                      Download markdown →
                    </a>
                  )}
                </div>
                {job?.result?.dimensions_in_graph === true && (
                  <p style={{ margin: 0, fontSize: "var(--text-caption)", color: "#166534" }}>
                    Dimensional snapshot was included in Trader and Portfolio Manager prompts for this run.
                  </p>
                )}
                {job?.result?.dimensions_in_graph === false && (
                  <p style={{ margin: 0, fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>
                    No in-graph dimensions snapshot (disabled, failed, or older run). Open{" "}
                    <strong>Dimensional study</strong> for post-pass scores when available.
                  </p>
                )}
              </section>

              <section aria-label="Decision summary">
                <h3
                  style={{
                    margin: "0 0 var(--spacing-12)",
                    fontSize: "var(--text-heading-sm)",
                    fontWeight: 600,
                    color: "var(--color-slate-text)",
                  }}
                >
                  At a glance
                </h3>
                <dl
                  style={{
                    margin: 0,
                    border: "1px solid var(--color-stone-border)",
                    borderRadius: "var(--radius-cards)",
                    overflow: "hidden",
                    background: "var(--surface-canvas-fog)",
                  }}
                >
                  {(
                    [
                      ["What to do now", decisionSummary.actionNow],
                      [
                        "Conviction",
                        decisionSummary.confidencePct != null
                          ? `${decisionSummary.confidencePct}% · ${decisionSummary.confidenceLabel}`
                          : decisionSummary.confidenceLabel,
                      ],
                      ["FOMO risk", decisionSummary.fomoLabel],
                      ["Time horizon", decisionSummary.horizon],
                    ] as const
                  ).map(([label, value], i, arr) => (
                    <div
                      key={label}
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "var(--spacing-4)",
                        padding: "var(--spacing-12) var(--spacing-16)",
                        borderBottom:
                          i < arr.length - 1 ? "1px solid var(--color-stone-border)" : undefined,
                      }}
                    >
                      <dt
                        style={{
                          margin: 0,
                          fontSize: "var(--text-caption)",
                          color: "var(--color-ash-gray)",
                          fontWeight: 500,
                        }}
                      >
                        {label}
                      </dt>
                      <dd style={{ margin: 0, fontWeight: 600, lineHeight: 1.35, color: "var(--color-slate-text)" }}>
                        {value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </section>

              <section aria-label="Context excerpt">
                <h3
                  style={{
                    margin: "0 0 var(--spacing-12)",
                    fontSize: "var(--text-heading-sm)",
                    fontWeight: 600,
                    color: "var(--color-slate-text)",
                  }}
                >
                  Context from the run
                </h3>
                <div
                  style={{
                    display: "grid",
                    gap: "var(--spacing-16)",
                    gridTemplateColumns: "repeat(auto-fit, minmax(17rem, 1fr))",
                    padding: "var(--spacing-24)",
                    background: "var(--surface-canvas-fog)",
                    border: "1px solid var(--color-stone-border)",
                    borderRadius: "var(--radius-cards)",
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: "var(--text-caption)",
                        fontWeight: 600,
                        color: "var(--color-steel-gray)",
                        marginBottom: "var(--spacing-8)",
                      }}
                    >
                      Why now
                    </div>
                    <ul
                      style={{
                        margin: 0,
                        paddingLeft: "var(--spacing-24)",
                        lineHeight: 1.55,
                      }}
                    >
                      {decisionSummary.whyNow.length ? (
                        decisionSummary.whyNow.map((line) => <li key={line}>{line}</li>)
                      ) : (
                        <li style={{ color: "var(--color-ash-gray)" }}>
                          No concise reason lines found in the generated report yet.
                        </li>
                      )}
                    </ul>
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: "var(--text-caption)",
                        fontWeight: 600,
                        color: "var(--color-steel-gray)",
                        marginBottom: "var(--spacing-8)",
                      }}
                    >
                      Invalidation
                    </div>
                    <p style={{ margin: 0, lineHeight: 1.55 }}>{decisionSummary.invalidation}</p>
                  </div>
                </div>
              </section>

              {job?.result?.analyst_coverage &&
              Object.keys(job.result.analyst_coverage).length > 0 ? (
                <section
                  aria-label="Analyst run summary"
                  style={{
                    marginBottom: "var(--spacing-16)",
                    padding: "var(--spacing-16)",
                    borderRadius: "var(--radius-md)",
                    border: "1px solid var(--color-stone-border)",
                    background: "var(--surface-canvas-fog)",
                  }}
                >
                  <div
                    style={{
                      fontSize: "var(--text-caption)",
                      fontWeight: 600,
                      color: "var(--color-steel-gray)",
                      marginBottom: "var(--spacing-8)",
                    }}
                  >
                    Analyst run summary
                  </div>
                  <p
                    style={{
                      margin: "0 0 var(--spacing-12)",
                      fontSize: 13,
                      color: "var(--color-slate-text)",
                      maxWidth: "72ch",
                      lineHeight: 1.5,
                    }}
                  >
                    Shows whether report text was captured after each analyst you selected.{' '}
                    <strong>empty</strong> usually means the model ended with pending tool calls (no final
                    narrative), a timeout, or empty structured fallback — see the matching section below for the same explanation.
                  </p>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ borderCollapse: "collapse", fontSize: 13, width: "100%" }}>
                      <thead>
                        <tr>
                          <th
                            style={{
                              textAlign: "left",
                              padding: "6px 8px",
                              borderBottom: "1px solid var(--color-stone-border)",
                            }}
                          >
                            Analyst
                          </th>
                          <th
                            style={{
                              textAlign: "left",
                              padding: "6px 8px",
                              borderBottom: "1px solid var(--color-stone-border)",
                            }}
                          >
                            Status
                          </th>
                          <th
                            style={{
                              textAlign: "left",
                              padding: "6px 8px",
                              borderBottom: "1px solid var(--color-stone-border)",
                            }}
                          >
                            Why / notes
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(job.result.analyst_coverage).map(([id, meta]) => (
                          <tr key={id}>
                            <td
                              style={{
                                padding: "6px 8px",
                                borderBottom: "1px solid var(--color-canvas-fog)",
                                verticalAlign: "top",
                              }}
                              className="mono"
                            >
                              {id}
                            </td>
                            <td
                              style={{
                                padding: "6px 8px",
                                borderBottom: "1px solid var(--color-canvas-fog)",
                                verticalAlign: "top",
                              }}
                            >
                              {meta.status === "ok" ? (
                                <span style={{ color: "#166534" }}>ok</span>
                              ) : meta.status === "empty" ? (
                                <span style={{ color: "#b45309" }}>empty</span>
                              ) : (
                                <span>{meta.status}</span>
                              )}
                              {typeof meta.chars === "number" ? (
                                <span style={{ color: "var(--color-ash-gray)", marginLeft: 6 }}>
                                  {meta.chars} chars
                                </span>
                              ) : null}
                            </td>
                            <td
                              style={{
                                padding: "6px 8px",
                                borderBottom: "1px solid var(--color-canvas-fog)",
                                verticalAlign: "top",
                                color: "var(--color-slate-text)",
                                lineHeight: 1.45,
                              }}
                            >
                              {meta.detail ?? "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              ) : null}

              <div
                className={
                  tocLevel2.length > 1
                    ? "dashboard-report-layout dashboard-report-layout--with-toc"
                    : "dashboard-report-layout"
                }
              >
                {tocLevel2.length > 1 && (
                  <nav
                    aria-label="Report sections"
                    className="dashboard-report-toc"
                  >
                    <div
                      style={{
                        fontWeight: 600,
                        marginBottom: "var(--spacing-8)",
                        color: "var(--color-slate-text)",
                      }}
                    >
                      Sections
                    </div>
                    <ul
                      style={{
                        margin: 0,
                        padding: 0,
                        listStyle: "none",
                        display: "grid",
                        gap: "var(--spacing-4)",
                      }}
                    >
                      {tocLevel2.map((t) => (
                        <li key={t.id}>
                          <a href={`#${t.id}`} style={{ color: "var(--color-chartwell-blue)" }}>
                            {t.text}
                          </a>
                        </li>
                      ))}
                    </ul>
                  </nav>
                )}
                <div className="markdown-body dashboard-report-markdown">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                    {mdReport}
                  </ReactMarkdown>
                </div>
              </div>
            </article>
          )}
        </div>
      )}
    </div>
  );
}
