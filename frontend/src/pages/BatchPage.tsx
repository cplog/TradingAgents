import { useAutoAnimate } from "@formkit/auto-animate/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Link, useSearchParams } from "react-router-dom";
import { Pressable } from "../components/Pressable";
import { PageFrame, PageHeader } from "../components/PageFrame";
import {
  fetchConfig,
  fetchHealth,
  filterAnalystsForBackend,
  mergeSupportedAnalystIds,
  getBatch,
  getJobDimensions,
  submitBatch,
  type JobStatus,
} from "../api";
import { FactorBar } from "../components/dimensions/FactorBar";
import { LlmPicker, llmConfigToOverrides, useLlmConfig } from "../components/LlmPicker";
import { topicPath, paths } from "../navigation/routes";
import type { FactorScores, StockDimensions } from "../dimensions-types";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { useJobsRefresh } from "../contexts/JobsTrackerContext";

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

const FACTOR_KEYS: (keyof FactorScores)[] = [
  "value",
  "growth",
  "quality",
  "momentum",
  "low_risk",
  "sentiment",
];

const FACTOR_LABELS: Record<keyof FactorScores, string> = {
  value: "Value",
  growth: "Growth",
  quality: "Quality",
  momentum: "Momentum",
  low_risk: "Low Risk",
  sentiment: "Sentiment",
};

type SortDir = "asc" | "desc";

function readInitialTickers(): string {
  if (typeof window === "undefined") return "AAPL, MSFT, GOOG";
  const params = new URLSearchParams(window.location.search);
  const raw = params.get("tickers");
  if (!raw) return "AAPL, MSFT, GOOG";
  const cleaned = raw
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  return cleaned.length ? cleaned.join(", ") : "AAPL, MSFT, GOOG";
}

export function BatchPage() {
  const refreshJobsRibbon = useJobsRefresh();
  const [batchBodyRef] = useAutoAnimate();
  const [rawTickers, setRawTickers] = useState<string>(() => readInitialTickers());
  const [selectedAnalysts, setSelectedAnalysts] = useState<string[]>(() =>
    ANALYST_OPTIONS.map((a) => a.id)
  );
  /** undefined = health loading; null = legacy; array = explicit allow-list */
  const [apiSupportedAnalystIds, setApiSupportedAnalystIds] = useState<string[] | null | undefined>(
    undefined
  );
  const [analystOmitNotice, setAnalystOmitNotice] = useState<string | null>(null);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [batch, setBatch] = useState<{ jobs: JobStatus[]; summary: Record<string, number> } | null>(
    null
  );
  const [err, setErr] = useState<string | null>(null);
  const [dimsByJob, setDimsByJob] = useState<Record<string, StockDimensions | null>>({});
  const [sortKey, setSortKey] = useState<keyof FactorScores | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [searchParams, setSearchParams] = useSearchParams();
  const { config: llmConfig, setConfig: setLlmConfig, hydrateFromServer: hydrateLlmFromServer, reset: resetLlm, serverDefaults } =
    useLlmConfig();

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
      if (cfg) hydrateLlmFromServer(cfg);
    });
    return () => {
      cancelled = true;
    };
  }, [hydrateLlmFromServer]);

  // Per-factor minimum-score filters persisted in URL (?min_value=50&min_growth=…)
  const filters = useMemo(() => {
    const out: Partial<Record<keyof FactorScores, number>> = {};
    FACTOR_KEYS.forEach((k) => {
      const raw = searchParams.get(`min_${k}`);
      if (raw != null && raw !== "") {
        const n = Number(raw);
        if (Number.isFinite(n)) out[k] = n;
      }
    });
    return out;
  }, [searchParams]);

  const setFilter = useCallback(
    (k: keyof FactorScores, value: string) => {
      const next = new URLSearchParams(searchParams);
      const cleaned = value.trim();
      if (!cleaned) {
        next.delete(`min_${k}`);
      } else {
        next.set(`min_${k}`, cleaned);
      }
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams]
  );

  const refresh = useCallback(async () => {
    if (!batchId) return;
    try {
      const b = await getBatch(batchId);
      setBatch({ jobs: b.jobs, summary: b.summary });
      setErr(null);
    } catch (e) {
      setErr(String(e));
    }
  }, [batchId]);

  useEffect(() => {
    if (!batchId) return;
    void refresh();
    const t = setInterval(() => void refresh(), 5000);
    return () => clearInterval(t);
  }, [batchId, refresh]);

  // Lazy-load dimensions for each completed job we don't have yet.
  useEffect(() => {
    if (!batch?.jobs?.length) return;
    let cancelled = false;
    const toFetch = batch.jobs.filter(
      (j) => j.status === "completed" && !(j.job_id in dimsByJob)
    );
    if (!toFetch.length) return;
    toFetch.forEach((j) => {
      void getJobDimensions(j.job_id)
        .then((b) => {
          if (cancelled) return;
          setDimsByJob((prev) => ({ ...prev, [j.job_id]: b.dimensions }));
        })
        .catch(() => {
          if (cancelled) return;
          setDimsByJob((prev) => ({ ...prev, [j.job_id]: null }));
        });
    });
    return () => {
      cancelled = true;
    };
  }, [batch?.jobs, dimsByJob]);

  async function run() {
    setErr(null);
    setAnalystOmitNotice(null);
    const tickers = rawTickers
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    const { analysts: analystsPayload, dropped } = filterAnalystsForBackend(
      selectedAnalysts,
      apiSupportedAnalystIds
    );
    if (dropped.length) {
      setAnalystOmitNotice(
        `Omitted analysts not supported by this API build: ${dropped.join(", ")}. Update/restart the API server from the current repo.`
      );
    }
    const r = await submitBatch({
      tickers,
      analysts: analystsPayload,
      config_overrides: llmConfigToOverrides(llmConfig),
    });
    refreshJobsRibbon();
    setBatchId(r.batch_id);
    setDimsByJob({});
  }

  function toggleSort(k: keyof FactorScores) {
    if (sortKey === k) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(k);
      setSortDir("desc");
    }
  }

  const visibleJobs = useMemo(() => {
    if (!batch?.jobs) return [];
    let rows = [...batch.jobs];
    // Apply per-factor min filters
    const activeFilters = Object.entries(filters) as [keyof FactorScores, number][];
    if (activeFilters.length > 0) {
      rows = rows.filter((j) => {
        const dims = dimsByJob[j.job_id];
        if (!dims) return false;
        return activeFilters.every(([k, min]) => {
          const score = dims.factor_scores[k]?.score;
          return score != null && score >= min;
        });
      });
    }
    // Sort by factor key (nulls last)
    if (sortKey) {
      rows.sort((a, b) => {
        const av = dimsByJob[a.job_id]?.factor_scores[sortKey]?.score ?? null;
        const bv = dimsByJob[b.job_id]?.factor_scores[sortKey]?.score ?? null;
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return sortDir === "desc" ? bv - av : av - bv;
      });
    }
    return rows;
  }, [batch?.jobs, filters, dimsByJob, sortKey, sortDir]);

  const tickerCount = useMemo(
    () =>
      rawTickers
        .split(/[\n,]+/)
        .map((s) => s.trim())
        .filter(Boolean).length,
    [rawTickers]
  );

  const estMinutes = useMemo(() => Math.max(1, Math.ceil(tickerCount * 3)), [tickerCount]);
  const topicFromUrl = searchParams.get("topic")?.trim() || null;
  useDocumentTitle(batchId ? `Batch ${batchId.slice(0, 8)}` : "Batch");

  return (
    <PageFrame className="content-entrance" wide>
      <PageHeader
        title="Batch analysis"
        description="Full multi-agent LLM run per ticker. Parallelism follows server max_concurrency."
        meta={
          <AppBreadcrumbs
            items={
              topicFromUrl
                ? [
                    { label: "Topics", to: paths.topics },
                    { label: topicFromUrl, to: topicPath(topicFromUrl) },
                    { label: "Batch" },
                  ]
                : [{ label: "Batch" }]
            }
          />
        }
      />
      {topicFromUrl ? (
        <div className="flow-banner topics-batch-banner" role="status">
          <strong>From topic:</strong> tickers pre-filled from theme{" "}
          <Link to={topicPath(topicFromUrl)}>{topicFromUrl}</Link>.{" "}
          <Link to={paths.topics}>Browse all topics</Link>
        </div>
      ) : null}
      <div className="flow-banner section-gap-sm">
        <strong>High cost / long runtime.</strong> Each ticker runs the full analyst → debate → PM pipeline (~3 min
        each). For a quick factor screen first, use Screener from the sidebar (facts-only, no LLM).
      </div>
      {analystOmitNotice ? (
        <p className="notice notice--warn" role="status">
          {analystOmitNotice}
        </p>
      ) : null}
      <label className="ui-field">
        <span className="ui-field__label">Tickers</span>
        <textarea
          className="ui-textarea"
          value={rawTickers}
          onChange={(e) => setRawTickers(e.target.value)}
          rows={4}
        />
      </label>
      {tickerCount > 0 && (
        <p className="ui-hint">
          {tickerCount} ticker{tickerCount === 1 ? "" : "s"} · rough estimate ~{estMinutes} min total (sequential
          mental model; server may run in parallel)
        </p>
      )}
      <details open className="batch-details">
        <summary className="batch-details__summary">LLM routing</summary>
        <div className="batch-details__body">
          <LlmPicker value={llmConfig} onChange={setLlmConfig} onReset={resetLlm} serverDefaults={serverDefaults} variant="compact" />
        </div>
      </details>
      <div className="section-gap-sm">
        <span className="ui-field__label">Focus area (analysts)</span>
        <div className="ui-form-row">
          {ANALYST_OPTIONS.map((a) => (
            <label key={a.id} className="ui-field-row">
              <input
                type="checkbox"
                checked={selectedAnalysts.includes(a.id)}
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
      </div>
      <Pressable
        className="ui-btn-primary"
        disabled={apiSupportedAnalystIds === undefined}
        onClick={() => void run().catch((e) => setErr(String(e)))}
      >
        {apiSupportedAnalystIds === undefined ? "Checking API…" : "Submit batch"}
      </Pressable>
      {batchId && (
        <p className="mono batch-id">
          batch_id: {batchId}
        </p>
      )}
      {err && <p className="notice notice--error">{err}</p>}

      <AnimatePresence>
        {batch && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0, transition: { duration: 0.25, ease: [0.25, 1, 0.5, 1] } }}
            exit={{ opacity: 0, y: -4, transition: { duration: 0.15, ease: [0.25, 1, 0.5, 1] } }}
          >
          <section className="stack-sm">
            <h2 style={{ margin: 0, fontSize: "var(--text-heading-sm)" }}>Summary</h2>
            <div className="batch-chips">
              {Object.entries(batch.summary).map(([k, v], i) => (
                <motion.span
                  key={k}
                  className="mono batch-chip"
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0, transition: { duration: 0.18, ease: [0.25, 1, 0.5, 1], delay: i * 0.04 } }}
                >
                  <span className="batch-chip__key">{k}</span>
                  {v}
                </motion.span>
              ))}
            </div>
          </section>

          <div className="filter-card">
            <div className="filter-card__title">Filter by minimum factor score (URL-persisted)</div>
            <div className="filter-card__body">
              {FACTOR_KEYS.map((k) => (
                <label key={k} className="filter-card__field">
                  <span>min {FACTOR_LABELS[k]}</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={filters[k] ?? ""}
                    placeholder="—"
                    onChange={(e) => setFilter(k, e.target.value)}
                    className="filter-card__num"
                  />
                </label>
              ))}
            </div>
          </div>

          <div className="batch-table-wrap">
            <table className="batch-table">
              <thead>
                <tr className="batch-table__head-row">
                  <th className="batch-table__th">Ticker</th>
                  <th className="batch-table__th">Status</th>
                  <th className="batch-table__th">Decision</th>
                  <th className="batch-table__th">Confidence</th>
                  {FACTOR_KEYS.map((k) => (
                    <th
                      key={k}
                      onClick={() => toggleSort(k)}
                      title={`Sort by ${FACTOR_LABELS[k]}`}
                      className="batch-table__th batch-table__th--sortable"
                    >
                      {FACTOR_LABELS[k]}
                      {sortKey === k ? (sortDir === "desc" ? " ▼" : " ▲") : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody ref={batchBodyRef}>
                {visibleJobs.map((j) => {
                  const dims = dimsByJob[j.job_id];
                  return (
                    <tr key={j.job_id} className="batch-table__row">
                      <td className="batch-table__td mono">
                        {j.ticker ?? j.result?.ticker ?? "—"}
                      </td>
                      <td className="batch-table__td">{j.status}</td>
                      <td className="batch-table__td">{j.result?.rating ?? "—"}</td>
                      <td className="batch-table__td">
                        {j.result?.confidence != null
                          ? `${(j.result.confidence * 100).toFixed(0)}%`
                          : "—"}
                      </td>
                      {FACTOR_KEYS.map((k) => (
                        <td key={k} className="batch-table__td batch-table__td--factor">
                          <FactorBar
                            label=""
                            score={dims?.factor_scores[k]?.score ?? null}
                            width={80}
                          />
                        </td>
                      ))}
                    </tr>
                  );
                })}
                {visibleJobs.length === 0 && (
                  <tr>
                    <td
                      colSpan={4 + FACTOR_KEYS.length}
                      className="batch-table__empty"
                    >
                      No jobs match the current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          </motion.div>
        )}
      </AnimatePresence>
    </PageFrame>
  );
}
