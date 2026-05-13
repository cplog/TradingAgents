import { useAutoAnimate } from "@formkit/auto-animate/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  deleteHistoryRun,
  fetchHistoryRun,
  fetchHistoryRuns,
  getDimensionsByTicker,
  getJobDimensions,
  postHistoryCompare,
  recomputeDimensions,
  type HistoryRunDetail,
  type HistoryCompareResponse,
  type HistoryRunRef,
} from "../api";
import { DimensionsPanel } from "../components/dimensions/DimensionsPanel";
import { DimensionsRadar } from "../components/dimensions/DimensionsRadar";
import { FactorBar } from "../components/dimensions/FactorBar";
import type { FactorScores, StockDimensions } from "../dimensions-types";

const FACTOR_KEYS: (keyof FactorScores)[] = [
  "value",
  "growth",
  "quality",
  "momentum",
  "low_risk",
  "sentiment",
];

type DetailTab = "report" | "dimensions";

function pct(conf: number | null | undefined): string {
  if (conf == null || !Number.isFinite(conf)) return "—";
  return `${Math.round(conf * 100)}%`;
}

function mdFromReports(reports: Record<string, string>, section?: string): string {
  if (section && reports[section]) {
    return `## ${section}\n\n${reports[section]}`;
  }
  return Object.entries(reports || {})
    .map(([k, v]) => `## ${k}\n\n${String(v)}`)
    .join("\n\n---\n\n");
}

export function HistoryPage() {
  const [runsBodyRef] = useAutoAnimate();
  const [runs, setRuns] = useState<HistoryRunRef[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tickerFilter, setTickerFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [runIdA, setRunIdA] = useState("");
  const [runIdB, setRunIdB] = useState("");
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [compare, setCompare] = useState<HistoryCompareResponse | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletingRunId, setDeletingRunId] = useState<string | null>(null);
  const [detailRunId, setDetailRunId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detail, setDetail] = useState<HistoryRunDetail | null>(null);
  const [showFullPm, setShowFullPm] = useState(false);
  const compareResultsRef = useRef<HTMLElement | null>(null);

  // Lazy-fetched per-row factor scores (facts-only preview) keyed by ticker
  const [thumbDims, setThumbDims] = useState<Record<string, StockDimensions | null>>({});
  // Detail-view tab + dimensions for the currently-opened run
  const [activeDetailTab, setActiveDetailTab] = useState<DetailTab>("report");
  const [detailDimensions, setDetailDimensions] = useState<StockDimensions | null>(null);
  const [detailDimensionsError, setDetailDimensionsError] = useState<string | null>(null);
  const [recomputing, setRecomputing] = useState(false);
  // Compare-side dimensions, fetched by ticker for each side
  const [compareDims, setCompareDims] = useState<{
    a: StockDimensions | null;
    b: StockDimensions | null;
  }>({ a: null, b: null });

  // Lazy-fetch thumbnail dimensions for each unique ticker visible in the table.
  // Falls back silently per ticker; failed fetches are remembered as null so we don't refetch.
  useEffect(() => {
    if (!runs.length) return;
    let cancelled = false;
    const uniqueTickers = Array.from(
      new Set(runs.map((r) => r.ticker).filter((t): t is string => Boolean(t)))
    );
    const missing = uniqueTickers.filter((t) => !(t in thumbDims));
    if (!missing.length) return;
    missing.forEach((t) => {
      void getDimensionsByTicker(t)
        .then((d) => {
          if (cancelled) return;
          setThumbDims((prev) => ({ ...prev, [t]: d }));
        })
        .catch(() => {
          if (cancelled) return;
          setThumbDims((prev) => ({ ...prev, [t]: null }));
        });
    });
    return () => {
      cancelled = true;
    };
  }, [runs, thumbDims]);

  // Fetch dimensions for the currently-open detail run
  useEffect(() => {
    if (!detail) {
      setDetailDimensions(null);
      setDetailDimensionsError(null);
      return;
    }
    let cancelled = false;
    setDetailDimensionsError(null);
    void getJobDimensions(detail.job_id)
      .then((d) => {
        if (!cancelled) setDetailDimensions(d);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setDetailDimensions(null);
        setDetailDimensionsError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [detail]);

  // Fetch compare-side dimensions (by ticker) when a compare response loads
  useEffect(() => {
    if (!compare) {
      setCompareDims({ a: null, b: null });
      return;
    }
    let cancelled = false;
    const aTicker = compare.a.ticker;
    const bTicker = compare.b.ticker;
    setCompareDims({ a: null, b: null });
    if (aTicker) {
      void getDimensionsByTicker(aTicker)
        .then((d) => {
          if (!cancelled) setCompareDims((prev) => ({ ...prev, a: d }));
        })
        .catch(() => {
          if (!cancelled) setCompareDims((prev) => ({ ...prev, a: null }));
        });
    }
    if (bTicker) {
      void getDimensionsByTicker(bTicker)
        .then((d) => {
          if (!cancelled) setCompareDims((prev) => ({ ...prev, b: d }));
        })
        .catch(() => {
          if (!cancelled) setCompareDims((prev) => ({ ...prev, b: null }));
        });
    }
    return () => {
      cancelled = true;
    };
  }, [compare]);

  useEffect(() => {
    if (compare && compareResultsRef.current) {
      const el = compareResultsRef.current;
      if (typeof el.scrollIntoView === "function") {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  }, [compare]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchHistoryRuns({
        ticker: tickerFilter.trim() || undefined,
        limit: 100,
        date_from: dateFrom.trim() || undefined,
        date_to: dateTo.trim() || undefined,
      });
      setRuns(list);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setRuns([]);
    } finally {
      setLoading(false);
    }
  }, [tickerFilter, dateFrom, dateTo]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchHistoryRuns({ limit: 100 })
      .then((list) => {
        if (!cancelled) {
          setRuns(list);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setRuns([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const runSelectOptions = useMemo(
    () =>
      runs.map((r) => ({
        id: r.run_id,
        label: `${r.ticker ?? "?"} · ${r.date ?? "?"} · ${r.run_id}${r.rating ? ` · ${r.rating}` : ""}`,
      })),
    [runs]
  );

  const compareReady =
    runSelectOptions.length >= 2 &&
    Boolean(runIdA.trim()) &&
    Boolean(runIdB.trim()) &&
    runIdA.trim() !== runIdB.trim();

  async function onCompare() {
    setCompareError(null);
    setCompareLoading(true);
    try {
      if (!runIdA.trim() || !runIdB.trim()) {
        throw new Error("Select two runs (A and B).");
      }
      if (runIdA.trim() === runIdB.trim()) {
        throw new Error("Choose two different run IDs.");
      }
      const payload = await postHistoryCompare(runIdA.trim(), runIdB.trim());
      setCompare(payload);
    } catch (e: unknown) {
      setCompare(null);
      setCompareError(e instanceof Error ? e.message : String(e));
    } finally {
      setCompareLoading(false);
    }
  }

  async function onDeleteRun(runId: string) {
    setDeleteError(null);
    setDeletingRunId(runId);
    try {
      await deleteHistoryRun(runId);
      setRuns((prev) => prev.filter((r) => r.run_id !== runId));
      if (runIdA === runId) setRunIdA("");
      if (runIdB === runId) setRunIdB("");
      if (compare?.a.run_id === runId || compare?.b.run_id === runId) {
        setCompare(null);
      }
      if (detailRunId === runId) {
        setDetailRunId(null);
        setDetail(null);
      }
    } catch (e: unknown) {
      setDeleteError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeletingRunId(null);
    }
  }

  async function onViewRun(runId: string) {
    if (detailRunId === runId && detail) return;
    setDetailError(null);
    setDetailLoading(true);
    setDetailRunId(runId);
    setActiveDetailTab("report");
    try {
      const payload = await fetchHistoryRun(runId);
      setDetail(payload);
    } catch (e: unknown) {
      setDetail(null);
      setDetailError(e instanceof Error ? e.message : String(e));
    } finally {
      setDetailLoading(false);
    }
  }

  async function onRecomputeDimensions() {
    if (!detail) return;
    setRecomputing(true);
    setDetailDimensionsError(null);
    try {
      await recomputeDimensions(detail.run_id);
      // Refetch dimensions for the current detail run
      const d = await getJobDimensions(detail.job_id);
      setDetailDimensions(d);
    } catch (e: unknown) {
      setDetailDimensionsError(e instanceof Error ? e.message : String(e));
    } finally {
      setRecomputing(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: "var(--spacing-24)", maxWidth: "90rem" }}>
      <header>
        <h1 style={{ fontSize: "var(--text-heading-lg)", margin: "0 0 8px" }}>
          History &amp; compare
        </h1>
        <p style={{ margin: 0, color: "var(--color-ash-gray)" }}>
          Durable runs from the API state store (Cloudflare KV when configured). Same ticker across dates
          or cross-ticker — choose two runs, then{" "}
          <strong>Use A / Use B</strong> in the table or the dropdowns. After Compare, the view scrolls to
          the pair below.
        </p>
      </header>

      <section
        style={{
          display: "grid",
          gap: "var(--spacing-16)",
          background: "var(--surface-cloud-white)",
          padding: "var(--card-padding)",
          borderRadius: "var(--radius-cards)",
          border: "1px solid var(--color-stone-border)",
          boxShadow: "var(--shadow-subtle)",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "var(--text-heading-sm)" }}>Filters</h2>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-12)", alignItems: "end" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 120 }}>
            <span style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>Ticker</span>
            <input
              value={tickerFilter}
              onChange={(e) => setTickerFilter(e.target.value)}
              placeholder="e.g. AAPL"
              style={{ padding: 8, borderRadius: "var(--radius-inputs)" }}
            />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>From</span>
            <input
              type="text"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              placeholder="YYYY-MM-DD"
              className="mono"
              style={{ padding: 8, borderRadius: "var(--radius-inputs)", width: 140 }}
            />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>To</span>
            <input
              type="text"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              placeholder="YYYY-MM-DD"
              className="mono"
              style={{ padding: 8, borderRadius: "var(--radius-inputs)", width: 140 }}
            />
          </label>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading}
            style={{
              padding: "10px 16px",
              borderRadius: "var(--radius-buttons)",
              border: "1px solid var(--color-stone-border)",
              background: "var(--color-chartwell-blue)",
              color: "white",
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "Loading…" : "Apply / refresh"}
          </button>
        </div>
        {error && (
          <div style={{ fontSize: "var(--text-caption)", color: "#991b1b" }}>{error}</div>
        )}
        {deleteError && (
          <div style={{ fontSize: "var(--text-caption)", color: "#991b1b" }}>{deleteError}</div>
        )}
      </section>

      <section
        style={{
          background: "var(--surface-cloud-white)",
          padding: "var(--card-padding)",
          borderRadius: "var(--radius-cards)",
          border: "1px solid var(--color-stone-border)",
          boxShadow: "var(--shadow-subtle)",
        }}
      >
        <h2 style={{ marginTop: 0 }}>Recent runs</h2>
        {runs.length === 0 && !loading ? (
          <p style={{ color: "var(--color-ash-gray)" }}>
            No history yet. Complete an analysis from the dashboard; runs are persisted when jobs finish.
          </p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "var(--text-caption)" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid var(--color-stone-border)" }}>
                  <th style={{ padding: "8px 6px" }}>Run ID</th>
                  <th style={{ padding: "8px 6px" }}>Ticker</th>
                  <th style={{ padding: "8px 6px" }}>Date</th>
                  <th style={{ padding: "8px 6px" }}>Rating</th>
                  <th style={{ padding: "8px 6px" }}>Confidence</th>
                  <th style={{ padding: "8px 6px" }}>Factors</th>
                  <th style={{ padding: "8px 6px" }}>Completed</th>
                  <th style={{ padding: "8px 6px", textAlign: "right" }} aria-label="Open run detail">
                    Detail
                  </th>
                  <th style={{ padding: "8px 6px", textAlign: "right" }} aria-label="Delete run">
                    Manage
                  </th>
                  <th style={{ padding: "8px 6px", textAlign: "right" }} aria-label="Set side A or B">
                    Compare
                  </th>
                </tr>
              </thead>
              <tbody ref={runsBodyRef}>
                {runs.map((r) => (
                  <tr key={r.run_id} style={{ borderBottom: "1px solid var(--color-platinum-outline)" }}>
                    <td style={{ padding: "8px 6px" }} className="mono">
                      {r.run_id}
                    </td>
                    <td style={{ padding: "8px 6px" }}>{r.ticker}</td>
                    <td style={{ padding: "8px 6px" }}>{r.date}</td>
                    <td style={{ padding: "8px 6px" }}>{r.rating ?? "—"}</td>
                    <td style={{ padding: "8px 6px" }}>{pct(r.confidence ?? undefined)}</td>
                    <td style={{ padding: "8px 6px" }}>
                      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        {FACTOR_KEYS.map((k) => (
                          <FactorBar
                            key={k}
                            label=""
                            score={
                              r.ticker
                                ? thumbDims[r.ticker]?.factor_scores[k]?.score ?? null
                                : null
                            }
                            width={36}
                          />
                        ))}
                      </div>
                    </td>
                    <td style={{ padding: "8px 6px" }} className="mono">
                      {r.completed_at ?? "—"}
                    </td>
                    <td style={{ padding: "8px 6px", textAlign: "right", verticalAlign: "middle" }}>
                      <button
                        type="button"
                        aria-label={`View run ${r.run_id}`}
                        disabled={detailLoading && detailRunId === r.run_id}
                        onClick={() => void onViewRun(r.run_id)}
                        style={{
                          padding: "4px 10px",
                          fontSize: 11,
                          fontWeight: 600,
                          borderRadius: "var(--radius-inputs)",
                          border: "1px solid var(--color-stone-border)",
                          background:
                            detailRunId === r.run_id ? "var(--color-sky-tint)" : "var(--surface-cloud-white)",
                          cursor:
                            detailLoading && detailRunId === r.run_id ? "not-allowed" : "pointer",
                        }}
                      >
                        {detailLoading && detailRunId === r.run_id ? "Loading…" : "View"}
                      </button>
                    </td>
                    <td style={{ padding: "8px 6px", textAlign: "right", verticalAlign: "middle" }}>
                      <button
                        type="button"
                        aria-label={`Delete run ${r.run_id}`}
                        disabled={deletingRunId === r.run_id}
                        onClick={() => {
                          if (!window.confirm(`Delete run ${r.run_id}? This cannot be undone.`)) return;
                          void onDeleteRun(r.run_id);
                        }}
                        style={{
                          padding: "4px 10px",
                          fontSize: 11,
                          fontWeight: 600,
                          borderRadius: "var(--radius-inputs)",
                          border: "1px solid #fecaca",
                          background: deletingRunId === r.run_id ? "#fee2e2" : "#fff1f2",
                          color: "#991b1b",
                          cursor: deletingRunId === r.run_id ? "not-allowed" : "pointer",
                        }}
                      >
                        {deletingRunId === r.run_id ? "Deleting…" : "Delete"}
                      </button>
                    </td>
                    <td style={{ padding: "8px 6px", textAlign: "right", verticalAlign: "middle" }}>
                      <div style={{ display: "inline-flex", flexWrap: "wrap", gap: 6, justifyContent: "flex-end" }}>
                        <button
                          type="button"
                          aria-label={`Use ${r.ticker ?? r.run_id} run ${r.run_id} as Compare side A`}
                          onClick={() => {
                            setRunIdA(r.run_id);
                            setCompareError(null);
                          }}
                          style={{
                            padding: "4px 8px",
                            fontSize: 11,
                            fontWeight: 600,
                            borderRadius: "var(--radius-inputs)",
                            border: "1px solid var(--color-stone-border)",
                            background:
                              runIdA === r.run_id ? "var(--color-sky-tint)" : "var(--surface-cloud-white)",
                            cursor: "pointer",
                          }}
                        >
                          A
                        </button>
                        <button
                          type="button"
                          aria-label={`Use ${r.ticker ?? r.run_id} run ${r.run_id} as Compare side B`}
                          onClick={() => {
                            setRunIdB(r.run_id);
                            setCompareError(null);
                          }}
                          style={{
                            padding: "4px 8px",
                            fontSize: 11,
                            fontWeight: 600,
                            borderRadius: "var(--radius-inputs)",
                            border: "1px solid var(--color-stone-border)",
                            background:
                              runIdB === r.run_id ? "var(--color-sky-tint)" : "var(--surface-cloud-white)",
                            cursor: "pointer",
                          }}
                        >
                          B
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {(detail || detailError || detailLoading) && (
        <section
          style={{
            display: "grid",
            gap: "var(--spacing-16)",
            background: "var(--surface-cloud-white)",
            padding: "var(--card-padding)",
            borderRadius: "var(--radius-cards)",
            border: "1px solid var(--color-stone-border)",
            boxShadow: "var(--shadow-subtle)",
          }}
        >
          <h2 style={{ marginTop: 0 }}>
            Run detail{detailRunId ? <span className="mono"> · {detailRunId}</span> : ""}
          </h2>
          {detailLoading && <p style={{ margin: 0 }}>Loading run detail…</p>}
          {detailError && <p style={{ margin: 0, color: "#991b1b" }}>{detailError}</p>}
          {detail && (
            <>
              <div style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>
                {detail.ticker} · {detail.date} · {detail.rating}
                {detail.confidence != null ? ` · ${pct(detail.confidence)}` : ""}
              </div>
              <div
                role="tablist"
                aria-label="Run detail sections"
                style={{
                  display: "flex",
                  gap: 4,
                  borderBottom: "1px solid var(--color-stone-border)",
                  marginBottom: "var(--spacing-8)",
                }}
              >
                {(["report", "dimensions"] as DetailTab[]).map((t) => (
                  <button
                    key={t}
                    type="button"
                    role="tab"
                    aria-selected={activeDetailTab === t}
                    onClick={() => setActiveDetailTab(t)}
                    style={{
                      padding: "6px 12px",
                      border: "none",
                      borderBottom:
                        activeDetailTab === t
                          ? "2px solid var(--color-chartwell-blue)"
                          : "2px solid transparent",
                      background: "transparent",
                      fontWeight: activeDetailTab === t ? 600 : 500,
                      cursor: "pointer",
                      textTransform: "capitalize",
                    }}
                  >
                    {t}
                  </button>
                ))}
              </div>
              {activeDetailTab === "report" && (
                <div className="markdown-body" style={{ maxWidth: "72ch" }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {mdFromReports(detail.reports || {})}
                  </ReactMarkdown>
                </div>
              )}
              {activeDetailTab === "dimensions" && (
                <div style={{ display: "grid", gap: 12 }}>
                  {!detailDimensions && !detailDimensionsError && (
                    <p style={{ margin: 0, color: "var(--color-ash-gray)" }}>
                      Loading dimensions…
                    </p>
                  )}
                  {!detailDimensions && (
                    <div>
                      <button
                        type="button"
                        onClick={() => void onRecomputeDimensions()}
                        disabled={recomputing}
                        style={{
                          padding: "8px 14px",
                          borderRadius: "var(--radius-buttons)",
                          border: "1px solid var(--color-stone-border)",
                          background: recomputing
                            ? "var(--color-platinum-outline)"
                            : "var(--color-chartwell-blue)",
                          color: "white",
                          cursor: recomputing ? "not-allowed" : "pointer",
                          fontWeight: 600,
                        }}
                      >
                        {recomputing ? "Recomputing…" : "Recompute dimensions"}
                      </button>
                    </div>
                  )}
                  <DimensionsPanel
                    dimensions={detailDimensions}
                    error={detailDimensionsError}
                  />
                </div>
              )}
            </>
          )}
        </section>
      )}

      <section
        style={{
          display: "grid",
          gap: "var(--spacing-16)",
          background: "var(--surface-cloud-white)",
          padding: "var(--card-padding)",
          borderRadius: "var(--radius-cards)",
          border: "1px solid var(--color-stone-border)",
          boxShadow: "var(--shadow-subtle)",
        }}
      >
        <h2 style={{ marginTop: 0 }}>Compare two runs</h2>
        <div style={{ display: "grid", gap: "var(--spacing-12)", maxWidth: 720 }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontWeight: 600 }}>Run A</span>
            <select
              value={runIdA}
              onChange={(e) => setRunIdA(e.target.value)}
              style={{ padding: 8 }}
            >
              <option value="">Select…</option>
              {runSelectOptions.map((o) => (
                <option key={`a-${o.id}`} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontWeight: 600 }}>Run B</span>
            <select
              value={runIdB}
              onChange={(e) => setRunIdB(e.target.value)}
              style={{ padding: 8 }}
            >
              <option value="">Select…</option>
              {runSelectOptions.map((o) => (
                <option key={`b-${o.id}`} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-12)", alignItems: "center" }}>
            <button
              type="button"
              disabled={compareLoading || !compareReady}
              onClick={() => void onCompare()}
              title={
                !compareReady
                  ? "Select two different runs in the dropdowns or with A/B in the table"
                  : "Load side-by-side comparison"
              }
              style={{
                padding: "12px 16px",
                borderRadius: "var(--radius-buttons)",
                border: "none",
                background:
                  compareLoading || !compareReady ? "var(--color-platinum-outline)" : "var(--color-chartwell-blue)",
                color: "white",
                fontWeight: 600,
                cursor: compareLoading || !compareReady ? "not-allowed" : "pointer",
              }}
            >
              {compareLoading ? "Comparing…" : "Compare"}
            </button>
            <button
              type="button"
              disabled={compareLoading || !runIdA.trim() || !runIdB.trim()}
              title="Swap which run is shown on the left vs right"
              onClick={() => {
                const ta = runIdA;
                setRunIdA(runIdB);
                setRunIdB(ta);
                setCompare(null);
              }}
              style={{
                padding: "10px 14px",
                borderRadius: "var(--radius-buttons)",
                border: "1px solid var(--color-stone-border)",
                background: "var(--surface-cloud-white)",
                fontWeight: 600,
                cursor: compareLoading || !runIdA.trim() || !runIdB.trim() ? "not-allowed" : "pointer",
              }}
            >
              Swap A ↔ B
            </button>
          </div>
        </div>
        {compareError && (
          <div style={{ fontSize: "var(--text-caption)", color: "#991b1b" }}>{compareError}</div>
        )}
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "var(--text-caption)" }}>
          <input
            type="checkbox"
            checked={showFullPm}
            onChange={(e) => setShowFullPm(e.target.checked)}
          />
          Show full Portfolio Manager section (markdown)
        </label>

        {runSelectOptions.length >= 2 && !compareReady && (
          <p style={{ margin: 0, fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>
            Pick <strong>two different</strong> runs — use table <strong>A</strong>/<strong>B</strong> or the dropdowns —
            then press <strong>Compare</strong>.
          </p>
        )}

        {compare && (
          <div ref={compareResultsRef} style={{ paddingTop: "var(--spacing-16)" }}>
            <h3 style={{ margin: "0 0 var(--spacing-12)", fontSize: "var(--text-heading-sm)" }}>
              Side-by-side (A left · B right)
            </h3>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 16,
                marginBottom: "var(--spacing-16)",
              }}
            >
              {(["a", "b"] as const).map((side) => {
                const dims = compareDims[side];
                return (
                  <div
                    key={`radar-${side}`}
                    style={{
                      background: "var(--surface-canvas-fog)",
                      borderRadius: "var(--radius-md)",
                      border: "1px solid var(--color-stone-border)",
                      padding: 12,
                    }}
                  >
                    <div
                      style={{
                        fontSize: "var(--text-caption)",
                        fontWeight: 600,
                        marginBottom: 6,
                      }}
                    >
                      {side === "a" ? "Run A · Dimensions" : "Run B · Dimensions"}
                    </div>
                    {dims ? (
                      <DimensionsRadar factorScores={dims.factor_scores} height={220} />
                    ) : (
                      <div
                        style={{
                          height: 220,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          color: "var(--color-ash-gray)",
                          fontSize: 12,
                        }}
                      >
                        Dimensions unavailable for this side.
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="compare-two-col">
              {[compare.a, compare.b].map((side, idx) => (
                <article
                  key={side.run_id ?? String(idx)}
                  style={{
                    background: "var(--surface-canvas-fog)",
                    padding: "var(--spacing-24)",
                    borderRadius: "var(--radius-largecard)",
                    border: "1px solid var(--color-stone-border)",
                    boxShadow: "var(--shadow-subtle)",
                    minWidth: 0,
                  }}
                >
                  <div style={{ marginBottom: "var(--spacing-16)" }}>
                    <div style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>
                      {idx === 0 ? "Run A (left)" : "Run B (right)"}
                    </div>
                    <div style={{ fontSize: "var(--text-heading)", fontWeight: 600 }}>
                      {side.rating ?? "—"}
                    </div>
                    <div className="mono" style={{ marginTop: 8, fontSize: "var(--text-caption)" }}>
                      {side.ticker ?? "—"} · {side.date ?? "—"}
                    </div>
                    <div style={{ marginTop: 6, fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>
                      Confidence: {pct(side.confidence ?? undefined)}
                    </div>
                    {side.run_id && (
                      <div className="mono" style={{ marginTop: 4, fontSize: 11, color: "var(--color-steel-gray)" }}>
                        {side.run_id}
                      </div>
                    )}
                    {side.config_snapshot && typeof side.config_snapshot.llm_provider === "string" && (
                      <div style={{ marginTop: 12, fontSize: 11, color: "var(--color-steel-gray)" }}>
                        Provider:{" "}
                        <span className="mono">{String(side.config_snapshot.llm_provider)}</span>
                      </div>
                    )}
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, marginBottom: 8 }}>Trader plan (excerpt)</div>
                    <pre
                      className="mono"
                      style={{
                        whiteSpace: "pre-wrap",
                        fontSize: 12,
                        background: "var(--surface-cloud-white)",
                        padding: 12,
                        borderRadius: "var(--radius-md)",
                        maxHeight: 220,
                        overflow: "auto",
                      }}
                    >
                      {side.excerpt_trader_plan || "—"}
                    </pre>
                  </div>
                  <div style={{ marginTop: "var(--spacing-16)" }}>
                    <div style={{ fontWeight: 600, marginBottom: 8 }}>Portfolio decision</div>
                    {showFullPm ? (
                      <div className="markdown-body" style={{ fontSize: 14 }}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {mdFromReports(side.reports || {}, "portfolio_decision")}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <pre
                        className="mono"
                        style={{
                          whiteSpace: "pre-wrap",
                          fontSize: 12,
                          background: "var(--surface-cloud-white)",
                          padding: 12,
                          borderRadius: "var(--radius-md)",
                          maxHeight: 280,
                          overflow: "auto",
                        }}
                      >
                        {side.excerpt_portfolio_decision || "—"}
                      </pre>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
