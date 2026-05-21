import { useAutoAnimate } from "@formkit/auto-animate/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
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
import type { FactorScores, StockDimensions } from "../dimensions-types";

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
  const { config: llmConfig, setConfig: setLlmConfig, hydrateFromServer: hydrateLlmFromServer, reset: resetLlm } =
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

  return (
    <PageFrame wide>
      <PageHeader
        title="Batch analysis"
        description="Full multi-agent LLM run per ticker. Parallelism follows server max_concurrency."
      />
      <div className="flow-banner">
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
        <p style={{ margin: "0 0 var(--spacing-12)", fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>
          {tickerCount} ticker{tickerCount === 1 ? "" : "s"} · rough estimate ~{estMinutes} min total (sequential
          mental model; server may run in parallel)
        </p>
      )}
      <details open style={{ marginTop: 12, marginBottom: 12 }}>
        <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: "var(--text-caption)" }}>
          LLM routing
        </summary>
        <div style={{ marginTop: 8 }}>
          <LlmPicker value={llmConfig} onChange={setLlmConfig} onReset={resetLlm} variant="compact" />
        </div>
      </details>
      <div style={{ marginTop: 12 }}>
        <span style={{ fontSize: "var(--text-caption)", display: "block", marginBottom: 6 }}>
          Focus area (analysts)
        </span>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
          {ANALYST_OPTIONS.map((a) => (
            <label key={a.id} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14 }}>
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
        <p className="mono" style={{ marginTop: 8 }}>
          batch_id: {batchId}
        </p>
      )}
      {err && <p className="notice notice--error">{err}</p>}

      {batch && (
        <>
          <section aria-label="Batch summary" style={{ display: "grid", gap: "var(--spacing-8)" }}>
            <h2 style={{ margin: 0, fontSize: "var(--text-heading-sm)" }}>Summary</h2>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-8)" }}>
              {Object.entries(batch.summary).map(([k, v]) => (
                <span
                  key={k}
                  className="mono"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    padding: "6px 12px",
                    borderRadius: "var(--radius-cards)",
                    border: "1px solid var(--color-stone-border)",
                    background: "var(--surface-cloud-white)",
                    fontSize: "var(--text-caption)",
                    color: "var(--color-slate-text)",
                  }}
                >
                  <span style={{ color: "var(--color-ash-gray)", marginRight: 6 }}>{k}</span>
                  {v}
                </span>
              ))}
            </div>
          </section>

          <div
            style={{
              marginBottom: 12,
              padding: 12,
              border: "1px solid var(--color-stone-border)",
              borderRadius: "var(--radius-md)",
              background: "var(--surface-canvas-fog)",
            }}
          >
            <div style={{ fontSize: "var(--text-caption)", fontWeight: 600, marginBottom: 6 }}>
              Filter by minimum factor score (URL-persisted)
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
              {FACTOR_KEYS.map((k) => (
                <label
                  key={k}
                  style={{ display: "flex", flexDirection: "column", fontSize: 12 }}
                >
                  <span>min {FACTOR_LABELS[k]}</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={filters[k] ?? ""}
                    placeholder="—"
                    onChange={(e) => setFilter(k, e.target.value)}
                    style={{ width: 72, padding: 4 }}
                  />
                </label>
              ))}
            </div>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                background: "var(--surface-cloud-white)",
                borderRadius: "var(--radius-md)",
                overflow: "hidden",
                boxShadow: "var(--shadow-subtle)",
                fontSize: 13,
              }}
            >
              <thead>
                <tr style={{ background: "var(--color-sky-tint)", textAlign: "left" }}>
                  <th style={{ padding: 12 }}>Ticker</th>
                  <th style={{ padding: 12 }}>Status</th>
                  <th style={{ padding: 12 }}>Decision</th>
                  <th style={{ padding: 12 }}>Confidence</th>
                  {FACTOR_KEYS.map((k) => (
                    <th
                      key={k}
                      onClick={() => toggleSort(k)}
                      title={`Sort by ${FACTOR_LABELS[k]}`}
                      style={{
                        padding: 12,
                        cursor: "pointer",
                        userSelect: "none",
                        whiteSpace: "nowrap",
                      }}
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
                    <tr key={j.job_id} style={{ borderTop: "1px solid var(--color-stone-border)" }}>
                      <td style={{ padding: 12 }} className="mono">
                        {j.ticker ?? j.result?.ticker ?? "—"}
                      </td>
                      <td style={{ padding: 12 }}>{j.status}</td>
                      <td style={{ padding: 12 }}>{j.result?.rating ?? "—"}</td>
                      <td style={{ padding: 12 }}>
                        {j.result?.confidence != null
                          ? `${(j.result.confidence * 100).toFixed(0)}%`
                          : "—"}
                      </td>
                      {FACTOR_KEYS.map((k) => (
                        <td key={k} style={{ padding: "4px 8px" }}>
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
                      style={{ padding: 16, textAlign: "center", color: "var(--color-ash-gray)" }}
                    >
                      No jobs match the current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </PageFrame>
  );
}
