import { useAutoAnimate } from "@formkit/auto-animate/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
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
import type { DimensionsCommentary, FactorScores, StockDimensions } from "../dimensions-types";
import type { Components } from "react-markdown";
import {
  orderedReportSectionKeys,
  prepareReportMarkdown,
  REPORT_SECTION_LABELS,
} from "../utils/reportMarkdown";

const REPORT_MD_COMPONENTS: Components = {
  table: ({ children, ...rest }) => (
    <div className="markdown-table-wrap">
      <table {...rest}>{children}</table>
    </div>
  ),
};

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

type RowFactorSource = "run_snapshot" | "live_preview" | "loading" | "unavailable";

function pickRowFactorScore(
  run: HistoryRunRef,
  tickerPreview: StockDimensions | null | undefined,
  key: keyof FactorScores,
): number | null {
  const runScore = run.factor_scores?.[key];
  if (typeof runScore === "number" && Number.isFinite(runScore)) {
    return runScore;
  }
  const previewScore = tickerPreview?.factor_scores[key]?.score;
  if (typeof previewScore === "number" && Number.isFinite(previewScore)) {
    return previewScore;
  }
  return null;
}

function inferRowFactorSource(
  run: HistoryRunRef,
  tickerPreview: StockDimensions | null | undefined,
): RowFactorSource {
  const hasRunSnapshot = FACTOR_KEYS.some((k) => {
    const v = run.factor_scores?.[k];
    return typeof v === "number" && Number.isFinite(v);
  });
  if (hasRunSnapshot) return "run_snapshot";
  if (!run.ticker) return "unavailable";
  if (tickerPreview === undefined) return "loading";
  if (tickerPreview?.factor_scores) return "live_preview";
  return "unavailable";
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
  const detailSectionRef = useRef<HTMLElement | null>(null);
  const detailFetchGen = useRef(0);

  // Lazy-fetched per-row factor scores (facts-only preview) keyed by ticker
  const [thumbDims, setThumbDims] = useState<Record<string, StockDimensions | null>>({});
  // Detail-view tab + dimensions for the currently-opened run
  const [activeDetailTab, setActiveDetailTab] = useState<DetailTab>("report");
  const [reportSectionKey, setReportSectionKey] = useState<string | null>(null);
  const [detailDimensions, setDetailDimensions] = useState<StockDimensions | null>(null);
  const [detailDimensionsCommentary, setDetailDimensionsCommentary] = useState<DimensionsCommentary | null>(null);
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
    const uniqueTickers = Array.from(new Set(
      runs
        .filter((r) => {
          if (!r.ticker) return false;
          const hasRunSnapshot = FACTOR_KEYS.some((k) => {
            const v = r.factor_scores?.[k];
            return typeof v === "number" && Number.isFinite(v);
          });
          return !hasRunSnapshot;
        })
        .map((r) => r.ticker)
        .filter((t): t is string => Boolean(t))
    ));
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
      setDetailDimensionsCommentary(null);
      setDetailDimensionsError(null);
      return;
    }
    if (detail.dimensions !== undefined || detail.dimensions_error !== undefined) {
      setDetailDimensions(detail.dimensions ?? null);
      setDetailDimensionsCommentary(detail.dimensions_commentary ?? null);
      setDetailDimensionsError(
        detail.dimensions_error && !detail.dimensions ? detail.dimensions_error : null
      );
      return;
    }
    let cancelled = false;
    setDetailDimensionsError(null);
    void getJobDimensions(detail.job_id)
      .then((b) => {
        if (cancelled) return;
        setDetailDimensions(b.dimensions);
        setDetailDimensionsCommentary(b.commentary);
        setDetailDimensionsError(b.error && !b.dimensions ? b.error : null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setDetailDimensions(null);
        setDetailDimensionsCommentary(null);
        setDetailDimensionsError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [detail]);

  useEffect(() => {
    if (!detail?.reports) {
      setReportSectionKey(null);
      return;
    }
    const keys = orderedReportSectionKeys(detail.reports);
    setReportSectionKey((prev) => {
      if (prev && keys.includes(prev)) return prev;
      return keys[0] ?? null;
    });
  }, [detail?.run_id, detail?.reports]);

  const reportMarkdown = useMemo(() => {
    if (!detail?.reports || !reportSectionKey) return "";
    const raw = detail.reports[reportSectionKey];
    if (!raw?.trim()) return "";
    return prepareReportMarkdown(reportSectionKey, raw);
  }, [detail?.reports, reportSectionKey]);

  const reportSectionKeys = useMemo(
    () => orderedReportSectionKeys(detail?.reports),
    [detail?.reports],
  );

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

  useEffect(() => {
    if (!detailRunId) return;
    const id = window.requestAnimationFrame(() => {
      const el = detailSectionRef.current;
      if (el && typeof el.scrollIntoView === "function") {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
    return () => cancelAnimationFrame(id);
  }, [detailRunId, detailLoading, detail, detailError]);

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
        detailFetchGen.current += 1;
        setDetailRunId(null);
        setDetail(null);
        setDetailLoading(false);
        setDetailError(null);
      }
    } catch (e: unknown) {
      setDeleteError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeletingRunId(null);
    }
  }

  function closeRunDetail() {
    detailFetchGen.current += 1;
    setDetailRunId(null);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(false);
  }

  async function onViewRun(runId: string) {
    if (detailRunId === runId && detail) return;
    const gen = ++detailFetchGen.current;
    setDetailError(null);
    setDetailLoading(true);
    setDetailRunId(runId);
    setActiveDetailTab("report");
    try {
      const payload = await fetchHistoryRun(runId);
      if (detailFetchGen.current !== gen) return;
      setDetail(payload);
    } catch (e: unknown) {
      if (detailFetchGen.current !== gen) return;
      setDetail(null);
      setDetailError(e instanceof Error ? e.message : String(e));
    } finally {
      if (detailFetchGen.current === gen) setDetailLoading(false);
    }
  }

  const [searchParams] = useSearchParams();
  const urlRunHandled = useRef(false);

  useEffect(() => {
    const ticker = searchParams.get("ticker")?.trim();
    if (ticker) setTickerFilter(ticker);
  }, [searchParams]);

  useEffect(() => {
    const run = searchParams.get("run")?.trim();
    if (!run || urlRunHandled.current) return;
    urlRunHandled.current = true;
    void onViewRun(run);
  }, [searchParams]);

  async function onRecomputeDimensions() {
    if (!detail) return;
    setRecomputing(true);
    setDetailDimensionsError(null);
    try {
      await recomputeDimensions(detail.run_id);
      // Refetch dimensions for the current detail run
      const b = await getJobDimensions(detail.job_id);
      setDetailDimensions(b.dimensions);
      setDetailDimensionsCommentary(b.commentary);
    } catch (e: unknown) {
      setDetailDimensionsError(e instanceof Error ? e.message : String(e));
    } finally {
      setRecomputing(false);
    }
  }

  return (
    <div className="history-page" style={{ display: "grid", gap: "var(--spacing-24)" }}>
      <header>
        <h1 style={{ fontSize: "var(--text-heading-lg)", margin: "0 0 8px" }}>
          History &amp; compare
        </h1>
        <p style={{ margin: 0, color: "var(--color-ash-gray)", maxWidth: "70ch", lineHeight: 1.55 }}>
          Durable runs from the API state store (Cloudflare KV when configured).{" "}
          <strong>Open a run</strong> to read reports and dimensions in the panel <strong>directly below filters</strong>, so
          a long table never sits above your content. Pick two runs with <strong>A / B</strong> or the Compare
          dropdowns; results open under Compare and the page scrolls there.
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

      {(detail || detailError || detailLoading) && (
        <section
          className="history-detail-card"
          ref={detailSectionRef}
          id="ta-history-run-detail"
          style={{
            display: "grid",
            gap: "var(--spacing-24)",
            background: "var(--surface-cloud-white)",
            padding: "clamp(var(--spacing-24), 3vw, var(--card-padding))",
            borderRadius: "var(--radius-largecard)",
            border: "1px solid var(--color-stone-border)",
            boxShadow: "var(--shadow-subtle)",
          }}
        >
          <header
            style={{
              display: "flex",
              flexWrap: "wrap",
              alignItems: "flex-start",
              justifyContent: "space-between",
              gap: "var(--spacing-12)",
            }}
          >
            <div style={{ display: "grid", gap: "var(--spacing-8)", minWidth: 0, flex: "1 1 16rem" }}>
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
                Selected run
              </p>
              <h2
                style={{
                  margin: 0,
                  fontSize: "var(--text-heading-sm)",
                  fontWeight: 600,
                  color: "var(--color-slate-text)",
                }}
              >
                Run detail
                {detailRunId ? (
                  <span
                    className="mono"
                    style={{
                      fontWeight: 500,
                      color: "var(--color-steel-gray)",
                      fontSize: "var(--text-caption)",
                    }}
                  >
                    {" "}
                    · {detailRunId}
                  </span>
                ) : null}
              </h2>
            </div>
            {detailRunId ? (
              <button
                type="button"
                onClick={closeRunDetail}
                style={{
                  padding: "8px 16px",
                  borderRadius: "var(--radius-buttons)",
                  border: "1px solid var(--color-stone-border)",
                  background: "var(--surface-canvas-fog)",
                  fontWeight: 600,
                  fontSize: "var(--text-caption)",
                  cursor: "pointer",
                  color: "var(--color-slate-text)",
                }}
              >
                Close
              </button>
            ) : null}
          </header>
          {detailLoading && <p style={{ margin: 0, color: "var(--color-ash-gray)" }}>Loading run detail…</p>}
          {detailError && <p style={{ margin: 0, color: "#991b1b" }}>{detailError}</p>}
          {detail && (
            <>
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
                  {detail.rating || "—"}
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
                    {detail.ticker}
                  </span>
                  <span>As of {detail.date}</span>
                  <span>
                    Conviction <span style={{ color: "var(--color-ash-gray)" }}>(heuristic)</span>:{" "}
                    {pct(detail.confidence ?? undefined)}
                  </span>
                  {detail.job_id ? (
                    <span className="mono" style={{ color: "var(--color-steel-gray)" }}>
                      job {detail.job_id}
                    </span>
                  ) : null}
                  {detail.completed_at ? <span>Completed {detail.completed_at}</span> : null}
                </div>
                {detail.dimensions_in_graph === true && (
                  <p style={{ margin: 0, fontSize: "var(--text-caption)", color: "#166534" }}>
                    Dimensional snapshot was included in Trader and Portfolio Manager prompts for this run.
                  </p>
                )}
                {detail.dimensions_in_graph === false && (
                  <p style={{ margin: 0, fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>
                    No in-graph dimensions snapshot on this persisted run. The Dimensions tab still shows scores from
                    storage or recompute when available.
                  </p>
                )}
              </section>

              <div
                role="tablist"
                aria-label="Run detail views"
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 8,
                  padding: 6,
                  background: "var(--surface-canvas-fog)",
                  borderRadius: "var(--radius-cards)",
                  border: "1px solid var(--color-stone-border)",
                }}
              >
                {(
                  [
                    { id: "report" as const, label: "Agent reports" },
                    { id: "dimensions" as const, label: "Dimensional study" },
                  ] as const
                ).map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    role="tab"
                    aria-selected={activeDetailTab === t.id}
                    onClick={() => setActiveDetailTab(t.id)}
                    style={{
                      padding: "10px 16px",
                      borderRadius: "var(--radius-buttons)",
                      border:
                        activeDetailTab === t.id
                          ? "1px solid var(--color-chartwell-blue)"
                          : "1px solid transparent",
                      background: activeDetailTab === t.id ? "var(--color-sky-tint)" : "transparent",
                      cursor: "pointer",
                      fontWeight: activeDetailTab === t.id ? 600 : 500,
                      color: "var(--color-slate-text)",
                      fontSize: "var(--text-caption)",
                    }}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {activeDetailTab === "report" && (
                <div className="history-report-view" style={{ display: "grid", gap: "var(--spacing-24)", minWidth: 0 }}>
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
                      Sections
                    </p>
                    <p
                      style={{
                        margin: 0,
                        fontSize: "var(--text-caption)",
                        color: "var(--color-ash-gray)",
                        maxWidth: "65ch",
                      }}
                    >
                      Research artifacts only, not financial advice. Pick a section to read; wide tables scroll
                      horizontally inside the content area.
                    </p>
                  </header>
                  <div
                    style={{
                      padding: "var(--spacing-16)",
                      borderRadius: "var(--radius-cards)",
                      border: "1px solid var(--color-stone-border)",
                      background: "var(--surface-canvas-fog)",
                      fontSize: "var(--text-caption)",
                      lineHeight: 1.55,
                      color: "var(--color-steel-gray)",
                    }}
                  >
                    Agent sections are LLM-generated from tools and public data; they can contain errors, repetition, or
                    off-topic padding (especially macro/news). Use fundamentals and tool-grounded facts when something
                    conflicts. HK/ADR names may appear with exchange suffixes; verify critical figures in primary sources.
                  </div>
                  {reportSectionKeys.length > 0 ? (
                    <div
                      className="history-report-sections"
                      role="tablist"
                      aria-label="Report sections"
                      style={{
                        display: "flex",
                        flexWrap: "nowrap",
                        gap: 8,
                        padding: 6,
                        background: "var(--surface-cloud-white)",
                        borderRadius: "var(--radius-cards)",
                        border: "1px solid var(--color-stone-border)",
                        overflowX: "auto",
                      }}
                    >
                      {reportSectionKeys.map((key) => (
                        <button
                          key={key}
                          type="button"
                          role="tab"
                          aria-selected={reportSectionKey === key}
                          onClick={() => setReportSectionKey(key)}
                          style={{
                            padding: "8px 14px",
                            borderRadius: "var(--radius-buttons)",
                            border:
                              reportSectionKey === key
                                ? "1px solid var(--color-chartwell-blue)"
                                : "1px solid var(--color-stone-border)",
                            background:
                              reportSectionKey === key ? "var(--color-sky-tint)" : "var(--surface-canvas-fog)",
                            fontSize: "var(--text-caption)",
                            fontWeight: reportSectionKey === key ? 600 : 500,
                            cursor: "pointer",
                            color: "var(--color-slate-text)",
                          }}
                        >
                          {REPORT_SECTION_LABELS[key] ?? key.replace(/_/g, " ")}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p style={{ margin: 0, color: "var(--color-ash-gray)" }}>No report sections stored.</p>
                  )}
                  <div className="history-report-body-wrap">
                    <div className="markdown-body history-report-body" style={{ maxWidth: "72ch", minWidth: 0 }}>
                      {reportMarkdown ? (
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={REPORT_MD_COMPONENTS}
                        >
                          {reportMarkdown}
                        </ReactMarkdown>
                      ) : (
                        <p style={{ margin: 0, color: "var(--color-ash-gray)" }}>Select a section above.</p>
                      )}
                    </div>
                  </div>
                </div>
              )}
              {activeDetailTab === "dimensions" && (
                <div style={{ display: "grid", gap: "var(--spacing-16)" }}>
                  {!detailDimensions && !detailDimensionsError && (
                    <p style={{ margin: 0, color: "var(--color-ash-gray)" }}>Loading dimensions…</p>
                  )}
                  {!detailDimensions && (
                    <div>
                      <button
                        type="button"
                        onClick={() => void onRecomputeDimensions()}
                        disabled={recomputing}
                        style={{
                          padding: "10px 16px",
                          borderRadius: "var(--radius-buttons)",
                          border: "none",
                          background: recomputing
                            ? "var(--color-platinum-outline)"
                            : "var(--color-chartwell-blue)",
                          color: "white",
                          cursor: recomputing ? "not-allowed" : "pointer",
                          fontWeight: 600,
                          fontSize: "var(--text-caption)",
                        }}
                      >
                        {recomputing ? "Recomputing…" : "Recompute dimensions"}
                      </button>
                    </div>
                  )}
                  <DimensionsPanel
                    dimensions={detailDimensions}
                    commentary={detailDimensionsCommentary}
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
          background: "var(--surface-cloud-white)",
          padding: "var(--card-padding)",
          borderRadius: "var(--radius-cards)",
          border: "1px solid var(--color-stone-border)",
          boxShadow: "var(--shadow-subtle)",
        }}
      >
        <h2 style={{ marginTop: 0 }}>Recent runs</h2>
        <p
          style={{
            margin: "0 0 var(--spacing-8)",
            fontSize: "var(--text-caption)",
            color: "var(--color-steel-gray)",
            lineHeight: 1.45,
          }}
        >
          <strong>View</strong> loads that row into the <strong>Selected run</strong> panel <strong>above</strong> this table (scrolls there automatically).
        </p>
        <p
          style={{
            margin: "0 0 var(--spacing-12)",
            fontSize: "var(--text-caption)",
            color: "var(--color-ash-gray)",
            lineHeight: 1.5,
          }}
        >
          <strong>Confidence</strong> is a shorthand tied to the final rating tier (for example Buy
          maps higher than Hold or Sell); it is not statistical certainty or “how good the data is.”
          <strong style={{ marginLeft: "0.35em" }}>Factors</strong> are six standardized scores
          (Value, Growth, Quality, Momentum, Low risk, Sentiment). The table now prefers each run&apos;s
          <em> persisted snapshot</em>; only rows missing stored factors fall back to a fresh
          facts-only ticker preview.
          Comparison is <strong>market-local peers first</strong> (exchange + currency + sector +
          industry), then sector-wide peers on the same listing, then a legacy global Yahoo
          sector/industry bucket (these broadening steps are surfaced as flags when they happen).
          Warm universes via{' '}
          <code style={{ fontSize: "0.95em" }}>scripts/warm_peer_cache.py global|local|sector</code>; when Cloudflare D1 env vars are set, warmed rows also mirror into D1.{' '}
          <strong>Why factors may show “—”:</strong> without enough cached peers relative scores are withheld to avoid pillar-only guesses; sentiment may still populate.
        </p>
        {runs.length === 0 && !loading ? (
          <p style={{ color: "var(--color-ash-gray)" }}>
            No history yet. Complete an analysis from the dashboard; runs are persisted when jobs finish.
          </p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="history-runs-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid var(--color-stone-border)" }}>
                  <th style={{ padding: "8px 6px" }}>Run ID</th>
                  <th style={{ padding: "8px 6px" }}>Ticker</th>
                  <th style={{ padding: "8px 6px" }}>Date</th>
                  <th style={{ padding: "8px 6px" }}>Rating</th>
                  <th
                    style={{ padding: "8px 6px" }}
                    title="Heuristic from final rating tier (e.g. Buy vs Hold vs Sell), not model uncertainty. See note above."
                  >
                    Confidence
                  </th>
                  <th
                    style={{ padding: "8px 6px" }}
                    title="Mini bars: six 0–100 factor scores. Source priority is persisted run snapshot first; if unavailable, the UI uses a current facts-only ticker preview and labels it."
                  >
                    Factors
                  </th>
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
                            score={pickRowFactorScore(r, r.ticker ? thumbDims[r.ticker] : null, k)}
                            width={36}
                          />
                        ))}
                        {(() => {
                          const source = inferRowFactorSource(
                            r,
                            r.ticker ? thumbDims[r.ticker] : null,
                          );
                          const label =
                            source === "run_snapshot"
                              ? "run"
                              : source === "live_preview"
                                ? "live"
                                : source === "loading"
                                  ? "loading"
                                  : "n/a";
                          return (
                            <span
                              style={{
                                marginTop: 2,
                                fontSize: 10,
                                lineHeight: 1.2,
                                color:
                                  source === "run_snapshot"
                                    ? "#166534"
                                    : source === "live_preview"
                                      ? "var(--color-steel-gray)"
                                      : "var(--color-ash-gray)",
                                textTransform: "uppercase",
                                letterSpacing: "0.03em",
                                fontWeight: 600,
                              }}
                              title={
                                source === "run_snapshot"
                                  ? "Using persisted factor scores captured with this run."
                                  : source === "live_preview"
                                    ? "Using current facts-only ticker preview because this run has no stored factors."
                                    : source === "loading"
                                      ? "Loading ticker preview factors."
                                      : "No factors available from run snapshot or ticker preview."
                              }
                            >
                              {label}
                            </span>
                          );
                        })()}
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

      <section
        style={{
          display: "grid",
          gap: "var(--spacing-24)",
          background: "var(--surface-cloud-white)",
          padding: "clamp(var(--spacing-24), 3vw, var(--card-padding))",
          borderRadius: "var(--radius-largecard)",
          border: "1px solid var(--color-stone-border)",
          boxShadow: "var(--shadow-subtle)",
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
            Tools
          </p>
          <h2 style={{ margin: 0, fontSize: "var(--text-heading-sm)", fontWeight: 600, color: "var(--color-slate-text)" }}>
            Compare two runs
          </h2>
          <p style={{ margin: 0, fontSize: "var(--text-caption)", color: "var(--color-ash-gray)", maxWidth: "65ch" }}>
            Choose sides from the table (A/B) or dropdowns, then load a structured pair view below.
          </p>
        </header>
        <div style={{ display: "grid", gap: "var(--spacing-16)", maxWidth: 720 }}>
          <label style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-8)" }}>
            <span style={{ fontWeight: 600, fontSize: "var(--text-caption)", color: "var(--color-slate-text)" }}>
              Run A
            </span>
            <select
              value={runIdA}
              onChange={(e) => setRunIdA(e.target.value)}
              style={{ padding: "var(--spacing-12)", borderRadius: "var(--radius-inputs)", border: "1px solid var(--color-stone-border)" }}
            >
              <option value="">Select…</option>
              {runSelectOptions.map((o) => (
                <option key={`a-${o.id}`} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-8)" }}>
            <span style={{ fontWeight: 600, fontSize: "var(--text-caption)", color: "var(--color-slate-text)" }}>
              Run B
            </span>
            <select
              value={runIdB}
              onChange={(e) => setRunIdB(e.target.value)}
              style={{ padding: "var(--spacing-12)", borderRadius: "var(--radius-inputs)", border: "1px solid var(--color-stone-border)" }}
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
          <div
            ref={compareResultsRef}
            style={{
              display: "grid",
              gap: "var(--spacing-24)",
              paddingTop: "var(--spacing-8)",
              borderTop: "1px solid var(--color-stone-border)",
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
                Comparison
              </p>
              <h3 style={{ margin: 0, fontSize: "var(--text-heading-sm)", fontWeight: 600, color: "var(--color-slate-text)" }}>
                Side-by-side · A left · B right
              </h3>
              <p style={{ margin: 0, fontSize: "var(--text-caption)", color: "var(--color-ash-gray)", maxWidth: "62ch" }}>
                Radar facets use a live facts-only fetch by ticker when available, not necessarily each run&apos;s as-of
                date. Read PM and trader excerpts in context.
              </p>
            </header>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 17rem), 1fr))",
                gap: "var(--spacing-16)",
              }}
            >
              {(["a", "b"] as const).map((side) => {
                const dims = compareDims[side];
                return (
                  <div
                    key={`radar-${side}`}
                    style={{
                      background: "var(--surface-canvas-fog)",
                      borderRadius: "var(--radius-cards)",
                      border: "1px solid var(--color-stone-border)",
                      padding: "var(--spacing-16)",
                      display: "grid",
                      gap: "var(--spacing-12)",
                    }}
                  >
                    <div
                      style={{
                        fontSize: "var(--text-caption)",
                        fontWeight: 600,
                        color: "var(--color-slate-text)",
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
                          fontSize: "var(--text-caption)",
                          textAlign: "center",
                          padding: "var(--spacing-16)",
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
                    background: "var(--surface-cloud-white)",
                    padding: "clamp(var(--spacing-16), 3vw, var(--spacing-24))",
                    borderRadius: "var(--radius-largecard)",
                    border: "1px solid var(--color-stone-border)",
                    boxShadow: "var(--shadow-md)",
                    minWidth: 0,
                    display: "grid",
                    gap: "var(--spacing-24)",
                  }}
                >
                  <section
                    style={{
                      display: "grid",
                      gap: "var(--spacing-16)",
                      paddingBottom: "var(--spacing-24)",
                      borderBottom: "1px solid var(--color-stone-border)",
                    }}
                  >
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
                      {idx === 0 ? "Run A" : "Run B"}
                    </p>
                    <div
                      style={{
                        fontSize: "var(--text-heading)",
                        fontWeight: 600,
                        letterSpacing: "-0.02em",
                        lineHeight: 1.2,
                        color: "var(--color-slate-text)",
                      }}
                    >
                      {side.rating ?? "—"}
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
                        {side.ticker ?? "—"}
                      </span>
                      <span>{side.date ? `As of ${side.date}` : "—"}</span>
                      <span>
                        Conviction <span style={{ color: "var(--color-ash-gray)" }}>(heuristic)</span>:{" "}
                        {pct(side.confidence ?? undefined)}
                      </span>
                    </div>
                    {side.run_id ? (
                      <div className="mono" style={{ fontSize: "var(--text-caption)", color: "var(--color-steel-gray)" }}>
                        {side.run_id}
                      </div>
                    ) : null}
                    {side.config_snapshot && typeof side.config_snapshot.llm_provider === "string" ? (
                      <div style={{ fontSize: "var(--text-caption)", color: "var(--color-steel-gray)" }}>
                        Provider:{" "}
                        <span className="mono" style={{ color: "var(--color-slate-text)" }}>
                          {String(side.config_snapshot.llm_provider)}
                        </span>
                      </div>
                    ) : null}
                  </section>

                  <section style={{ display: "grid", gap: "var(--spacing-12)", minWidth: 0 }}>
                    <h4
                      style={{
                        margin: 0,
                        fontSize: "var(--text-heading-sm)",
                        fontWeight: 600,
                        color: "var(--color-slate-text)",
                      }}
                    >
                      Trader plan (excerpt)
                    </h4>
                    <pre
                      className="mono"
                      style={{
                        margin: 0,
                        whiteSpace: "pre-wrap",
                        fontSize: "var(--text-caption)",
                        lineHeight: 1.55,
                        background: "var(--surface-canvas-fog)",
                        border: "1px solid var(--color-stone-border)",
                        padding: "var(--spacing-16)",
                        borderRadius: "var(--radius-cards)",
                        maxHeight: 220,
                        overflow: "auto",
                      }}
                    >
                      {side.excerpt_trader_plan || "—"}
                    </pre>
                  </section>

                  <section style={{ display: "grid", gap: "var(--spacing-12)", minWidth: 0 }}>
                    <h4
                      style={{
                        margin: 0,
                        fontSize: "var(--text-heading-sm)",
                        fontWeight: 600,
                        color: "var(--color-slate-text)",
                      }}
                    >
                      Portfolio decision
                    </h4>
                    {showFullPm ? (
                      <div
                        className="markdown-body"
                        style={{
                          fontSize: "var(--text-caption)",
                          padding: "var(--spacing-16)",
                          background: "var(--surface-canvas-fog)",
                          border: "1px solid var(--color-stone-border)",
                          borderRadius: "var(--radius-cards)",
                          maxHeight: 360,
                          overflow: "auto",
                        }}
                      >
                        {side.reports?.portfolio_decision?.trim() ? (
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={REPORT_MD_COMPONENTS}
                          >
                            {prepareReportMarkdown(
                              "portfolio_decision",
                              side.reports.portfolio_decision,
                            )}
                          </ReactMarkdown>
                        ) : (
                          <span style={{ color: "var(--color-ash-gray)" }}>—</span>
                        )}
                      </div>
                    ) : (
                      <pre
                        className="mono"
                        style={{
                          margin: 0,
                          whiteSpace: "pre-wrap",
                          fontSize: "var(--text-caption)",
                          lineHeight: 1.55,
                          background: "var(--surface-canvas-fog)",
                          border: "1px solid var(--color-stone-border)",
                          padding: "var(--spacing-16)",
                          borderRadius: "var(--radius-cards)",
                          maxHeight: 280,
                          overflow: "auto",
                        }}
                      >
                        {side.excerpt_portfolio_decision || "—"}
                      </pre>
                    )}
                  </section>
                </article>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
