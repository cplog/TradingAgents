import { useAutoAnimate } from "@formkit/auto-animate/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Pressable } from "../components/Pressable";
import {
  getBatch,
  getJobDimensions,
  submitBatch,
  type JobStatus,
} from "../api";
import { FactorBar } from "../components/dimensions/FactorBar";
import type { FactorScores, StockDimensions } from "../dimensions-types";

const ANALYST_OPTIONS = [
  { id: "market", label: "Market" },
  { id: "social", label: "Social Media" },
  { id: "news", label: "News" },
  { id: "fundamentals", label: "Fundamentals" },
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

export function BatchPage() {
  const [batchBodyRef] = useAutoAnimate();
  const [rawTickers, setRawTickers] = useState("AAPL, MSFT, GOOG");
  const [selectedAnalysts, setSelectedAnalysts] = useState<string[]>([
    "market",
    "social",
    "news",
    "fundamentals",
  ]);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [batch, setBatch] = useState<{ jobs: JobStatus[]; summary: Record<string, number> } | null>(
    null
  );
  const [err, setErr] = useState<string | null>(null);
  const [dimsByJob, setDimsByJob] = useState<Record<string, StockDimensions | null>>({});
  const [sortKey, setSortKey] = useState<keyof FactorScores | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [searchParams, setSearchParams] = useSearchParams();

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
    const tickers = rawTickers
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    const r = await submitBatch({
      tickers,
      analysts: selectedAnalysts.length ? selectedAnalysts : undefined,
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

  return (
    <div style={{ display: "grid", gap: "var(--spacing-24)", maxWidth: "1200px" }}>
      <header>
        <h1 style={{ margin: 0, fontSize: "var(--text-heading-lg)" }}>Batch analysis</h1>
        <p style={{ margin: "var(--spacing-8) 0 0", color: "var(--color-ash-gray)", maxWidth: "62ch" }}>
          Comma or newline separated tickers. Parallelism follows server{" "}
          <span className="mono">max_concurrency</span>.
        </p>
      </header>
      <textarea
        value={rawTickers}
        onChange={(e) => setRawTickers(e.target.value)}
        rows={4}
        style={{
          width: "100%",
          padding: "var(--spacing-12)",
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--color-platinum-outline)",
          fontFamily: "inherit",
        }}
      />
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
        onClick={() => void run().catch((e) => setErr(String(e)))}
        style={{
          marginTop: 12,
          padding: "10px 20px",
          borderRadius: "var(--radius-buttons)",
          background: "var(--color-chartwell-blue)",
          color: "white",
          border: "none",
          fontWeight: 600,
          cursor: "pointer",
        }}
      >
        Submit batch
      </Pressable>
      {batchId && (
        <p className="mono" style={{ marginTop: 8 }}>
          batch_id: {batchId}
        </p>
      )}
      {err && <p style={{ color: "#b91c1c" }}>{err}</p>}

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
    </div>
  );
}
