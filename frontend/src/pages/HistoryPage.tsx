import { useAutoAnimate } from "@formkit/auto-animate/react";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";
import { runsPath, stocksPath } from "../navigation/routes";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  bulkDeleteHistoryRuns,
  deleteAllHistoryRuns,
  deleteHistoryRun,
  fetchHistoryRun,
  fetchHistoryRuns,
  fetchJobs,
  getDimensionsByTicker,
  postHistoryCompare,
  submitAnalyze,
  submitBatch,
  type HistoryCompareResponse,
  type HistoryRunRef,
} from "../api";
import { HistoryTickerCards } from "../components/history/HistoryTickerCards";
import { RunProvenancePanel } from "../components/history/RunProvenancePanel";
import type { TickerRollup } from "../utils/historyRollup";
import { buildRerunAnalyzePayload } from "../utils/historyRerun";
import {
  formatHistoryTimestampWithZone,
  hasActiveHistoryRows,
  mergeHistoryAndJobs,
  sortHistoryRows,
  statusLabel,
  type HistorySortKey,
  type HistoryTableRow,
} from "../utils/historyDisplay";
import {
  formatLlmLabel,
  formatSourcesLabel,
  hasBiasWarning,
  provenanceTitle,
} from "../utils/runProvenance";
import { DimensionsPanel } from "../components/dimensions/DimensionsPanel";
import { DimensionsRadar } from "../components/dimensions/DimensionsRadar";
import { FactorBar } from "../components/dimensions/FactorBar";
import type { FactorScores, StockDimensions } from "../dimensions-types";
import type { Components } from "react-markdown";
import {
  orderedReportSectionKeys,
  prepareReportMarkdown,
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

function pct(conf: number | null | undefined): string {
  if (conf == null || !Number.isFinite(conf)) return "—";
  return `${Math.round(conf * 100)}%`;
}

type RowFactorSource = "run_snapshot" | "live_preview" | "loading" | "unavailable";

function pickRowFactorScore(
  run: HistoryTableRow,
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
  run: HistoryTableRow,
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
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const urlRunHandled = useRef(false);
  /** Rows the user deleted this session — filters live-job merge until refresh clears worker. */
  const hiddenRunIdsRef = useRef<Set<string>>(new Set());
  const [runsBodyRef] = useAutoAnimate();
  const [runs, setRuns] = useState<HistoryTableRow[]>([]);
  const [sortKey, setSortKey] = useState<HistorySortKey>("processing_desc");
  const [includeLiveJobs, setIncludeLiveJobs] = useState(true);
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
  const [selectedRunIds, setSelectedRunIds] = useState<Set<string>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [showFullPm, setShowFullPm] = useState(false);
  const compareResultsRef = useRef<HTMLElement | null>(null);

  const [viewMode, setViewMode] = useState<"cards" | "table">("cards");
  const [selectedTickers, setSelectedTickers] = useState<Set<string>>(new Set());
  const [rerunPendingTickers, setRerunPendingTickers] = useState<Set<string>>(new Set());
  const [rerunError, setRerunError] = useState<string | null>(null);
  const [bulkRerunSubmitting, setBulkRerunSubmitting] = useState(false);
  // Lazy-fetched per-row factor scores (facts-only preview) keyed by ticker
  const [thumbDims, setThumbDims] = useState<Record<string, StockDimensions | null>>({});
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
      const filters = {
        ticker: tickerFilter.trim() || undefined,
        dateFrom: dateFrom.trim() || undefined,
        dateTo: dateTo.trim() || undefined,
      };
      const [history, jobs] = await Promise.all([
        fetchHistoryRuns({
          ticker: filters.ticker,
          limit: 100,
          date_from: filters.dateFrom,
          date_to: filters.dateTo,
        }),
        includeLiveJobs ? fetchJobs(80) : Promise.resolve([]),
      ]);
      const merged = mergeHistoryAndJobs(history, jobs, filters).filter(
        (r) => !hiddenRunIdsRef.current.has(r.run_id),
      );
      setRuns(merged);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setRuns([]);
    } finally {
      setLoading(false);
    }
  }, [tickerFilter, dateFrom, dateTo, includeLiveJobs]);

  const sortedRuns = useMemo(
    () => sortHistoryRows(runs, sortKey),
    [runs, sortKey],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!includeLiveJobs || !hasActiveHistoryRows(runs)) return;
    const id = window.setInterval(() => {
      void refresh();
    }, 10000);
    return () => window.clearInterval(id);
  }, [includeLiveJobs, runs, refresh]);

  const runSelectOptions = useMemo(
    () =>
      sortedRuns
        .filter((r) => r.job_status === "completed")
        .map((r) => ({
          id: r.run_id,
          label: `${r.ticker ?? "?"} · ${r.date ?? "?"} · ${r.run_id}${r.rating ? ` · ${r.rating}` : ""}`,
        })),
    [sortedRuns]
  );

  const selectableRuns = useMemo(
    () =>
      sortedRuns.filter((r) =>
        r.job_status === "completed" ||
        r.job_status === "failed" ||
        r.job_status === "cancelled",
      ),
    [sortedRuns],
  );

  const allRunsSelected =
    selectableRuns.length > 0 && selectableRuns.every((r) => selectedRunIds.has(r.run_id));

  const compareReady =
    runSelectOptions.length >= 2 &&
    Boolean(runIdA.trim()) &&
    Boolean(runIdB.trim()) &&
    runIdA.trim() !== runIdB.trim();

  function openRunRow(row: HistoryTableRow) {
    openRun(row.job_id);
  }

  function statusBadgeStyle(status: HistoryTableRow["job_status"]): CSSProperties {
    switch (status) {
      case "running":
        return { background: "#dbeafe", color: "#1d4ed8", border: "1px solid #93c5fd" };
      case "queued":
        return { background: "#f3f4f6", color: "#374151", border: "1px solid #d1d5db" };
      case "failed":
        return { background: "#fee2e2", color: "#991b1b", border: "1px solid #fecaca" };
      case "cancelled":
        return { background: "#f3f4f6", color: "#6b7280", border: "1px solid #e5e7eb" };
      default:
        return { background: "#ecfdf5", color: "#166534", border: "1px solid #bbf7d0" };
    }
  }

  function pruneAfterDeletes(deletedIds: string[]) {
    const gone = new Set(deletedIds);
    deletedIds.forEach((id) => hiddenRunIdsRef.current.add(id));
    setRuns((prev) => prev.filter((r) => !gone.has(r.run_id)));
    setSelectedRunIds((prev) => {
      const next = new Set(prev);
      deletedIds.forEach((id) => next.delete(id));
      return next;
    });
    if (deletedIds.includes(runIdA)) setRunIdA("");
    if (deletedIds.includes(runIdB)) setRunIdB("");
    if (compare && (gone.has(compare.a.run_id ?? "") || gone.has(compare.b.run_id ?? ""))) {
      setCompare(null);
    }
  }

  function toggleRunSelection(runId: string) {
    setSelectedRunIds((prev) => {
      const next = new Set(prev);
      if (next.has(runId)) next.delete(runId);
      else next.add(runId);
      return next;
    });
  }

  function toggleSelectAllVisible() {
    if (allRunsSelected) {
      setSelectedRunIds(new Set());
      return;
    }
    setSelectedRunIds(new Set(selectableRuns.map((r) => r.run_id)));
  }

  async function onDeleteSelected() {
    const ids = [...selectedRunIds];
    if (!ids.length) return;
    if (
      !window.confirm(
        `Delete ${ids.length} selected run${ids.length === 1 ? "" : "s"}? This cannot be undone.`,
      )
    ) {
      return;
    }
    setDeleteError(null);
    setBulkDeleting(true);
    try {
      const result = await bulkDeleteHistoryRuns(ids);
      const removedFromView = [
        ...result.deleted_run_ids,
        ...result.missing_run_ids,
      ];
      pruneAfterDeletes(removedFromView);
      if (result.missing_run_ids.length) {
        const stale = result.missing_run_ids.join(", ");
        setDeleteError(
          result.deleted_count > 0
            ? `Removed ${result.deleted_count} from storage; cleared ${result.missing_run_ids.length} stale row(s) from the list (${stale}). Refresh if any reappear.`
            : `Cleared ${result.missing_run_ids.length} stale row(s) from the list (${stale}). They were not in history or job storage.`,
        );
      }
    } catch (e: unknown) {
      setDeleteError(e instanceof Error ? e.message : String(e));
    } finally {
      setBulkDeleting(false);
    }
  }

  async function onDeleteAllMatchingFilters() {
    const parts: string[] = [];
    if (tickerFilter.trim()) parts.push(`ticker ${tickerFilter.trim().toUpperCase()}`);
    if (dateFrom.trim()) parts.push(`from ${dateFrom.trim()}`);
    if (dateTo.trim()) parts.push(`to ${dateTo.trim()}`);
    const scope = parts.length ? ` matching ${parts.join(", ")}` : "";
    if (
      !window.confirm(
        `Delete all history runs${scope}? This cannot be undone.`,
      )
    ) {
      return;
    }
    setDeleteError(null);
    setBulkDeleting(true);
    try {
      const result = await deleteAllHistoryRuns({
        confirm: true,
        ticker: tickerFilter.trim() || undefined,
        date_from: dateFrom.trim() || undefined,
        date_to: dateTo.trim() || undefined,
      });
      setSelectedRunIds(new Set());
      setRunIdA("");
      setRunIdB("");
      setCompare(null);
      await refresh();
      if (result.deleted_count === 0) {
        setDeleteError("No runs matched the current filters.");
      }
    } catch (e: unknown) {
      setDeleteError(e instanceof Error ? e.message : String(e));
    } finally {
      setBulkDeleting(false);
    }
  }

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
      pruneAfterDeletes([runId]);
    } catch (e: unknown) {
      setDeleteError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeletingRunId(null);
    }
  }


  function openRun(runId: string) {
    navigate(runsPath(runId));
  }

  useEffect(() => {
    const ticker = searchParams.get("ticker")?.trim();
    if (!ticker) return;
    navigate(stocksPath(ticker), { replace: true });
  }, [searchParams, navigate]);

  useEffect(() => {
    const run = searchParams.get("run")?.trim();
    if (!run || urlRunHandled.current) return;
    urlRunHandled.current = true;
    navigate(runsPath(run), { replace: true });
  }, [searchParams, navigate]);



  function toggleTickerSelection(ticker: string) {
    setSelectedTickers((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  }

  async function onCardRerun(rollup: TickerRollup) {
    const baseRun = rollup.latestCompletedRun;
    if (!baseRun) return;
    setRerunError(null);
    setRerunPendingTickers((prev) => {
      const next = new Set(prev);
      next.add(rollup.ticker);
      return next;
    });
    try {
      const detailPayload = await fetchHistoryRun(baseRun.run_id);
      const body = buildRerunAnalyzePayload(detailPayload);
      const r = await submitAnalyze(body);
      // Send the user to the live run page; ribbon will keep showing chip too.
      navigate(runsPath(r.job_id));
    } catch (e: unknown) {
      setRerunError(e instanceof Error ? e.message : String(e));
    } finally {
      setRerunPendingTickers((prev) => {
        const next = new Set(prev);
        next.delete(rollup.ticker);
        return next;
      });
    }
  }

  function onCardOpenLatest(rollup: TickerRollup) {
    const row = rollup.latestCompletedRun ?? rollup.latestRun;
    if (!row) return;
    if (row.job_status === "completed") {
      openRun(row.run_id);
      return;
    }
    const jobId = row.job_id ?? row.run_id;
    navigate(runsPath(jobId));
  }

  async function onBulkRerunSelected() {
    const tickers = [...selectedTickers].filter(Boolean);
    if (!tickers.length) return;
    if (
      !window.confirm(
        `Submit a batch re-run for ${tickers.length} ticker${tickers.length === 1 ? "" : "s"}? Defaults from /admin will apply.`,
      )
    ) {
      return;
    }
    setRerunError(null);
    setBulkRerunSubmitting(true);
    try {
      const r = await submitBatch({ tickers });
      setSelectedTickers(new Set());
      navigate(`/batch?id=${encodeURIComponent(r.batch_id)}`);
    } catch (e: unknown) {
      setRerunError(e instanceof Error ? e.message : String(e));
    } finally {
      setBulkRerunSubmitting(false);
    }
  }



  return (
    <div className="history-page" style={{ display: "grid", gap: "var(--spacing-24)" }}>
      <header style={{ display: "grid", gap: "var(--spacing-12)" }}>
        <div>
          <h1 style={{ fontSize: "var(--text-heading-lg)", margin: "0 0 8px" }}>
            Runs &amp; compare
          </h1>
          <p style={{ margin: 0, color: "var(--color-ash-gray)", maxWidth: "70ch", lineHeight: 1.55 }}>
            Durable completed runs plus live jobs (queued/running/failed) from the API worker.
            Times are shown in <strong>Hong Kong (HKT)</strong>. Default sort is newest processing time first.
            {" "}
            <strong>Open run</strong> for the full report; click a <strong>ticker</strong> for stock-level history and compare.
          </p>
        </div>
        <AppBreadcrumbs items={[{ label: "Runs" }]} />
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
          <label style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 220 }}>
            <span style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>Sort by</span>
            <select
              aria-label="Sort history runs"
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as HistorySortKey)}
              style={{ padding: 8, borderRadius: "var(--radius-inputs)" }}
            >
              <option value="processing_desc">Processing time (newest first)</option>
              <option value="processing_asc">Processing time (oldest first)</option>
              <option value="trade_date_desc">Trade date (newest)</option>
              <option value="trade_date_asc">Trade date (oldest)</option>
              <option value="ticker_asc">Ticker (A→Z)</option>
              <option value="ticker_desc">Ticker (Z→A)</option>
              <option value="rating_desc">Rating (bullish first)</option>
              <option value="rating_asc">Rating (bearish first)</option>
              <option value="confidence_desc">Confidence (high first)</option>
              <option value="confidence_asc">Confidence (low first)</option>
              <option value="status_desc">Status (active first)</option>
              <option value="status_asc">Status (completed first)</option>
            </select>
          </label>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontSize: "var(--text-caption)",
              color: "var(--color-steel-gray)",
              paddingBottom: 8,
            }}
          >
            <input
              type="checkbox"
              checked={includeLiveJobs}
              onChange={(e) => setIncludeLiveJobs(e.target.checked)}
            />
            Include in-progress jobs
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
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "var(--spacing-12)",
            marginBottom: "var(--spacing-12)",
          }}
        >
          <h2 style={{ margin: 0 }}>Recent runs ({sortedRuns.length})</h2>
          <div
            role="tablist"
            aria-label="Recent runs view mode"
            style={{
              display: "inline-flex",
              padding: 4,
              gap: 4,
              background: "var(--surface-canvas-fog)",
              borderRadius: "var(--radius-cards)",
              border: "1px solid var(--color-stone-border)",
            }}
          >
            {(["cards", "table"] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="tab"
                aria-selected={viewMode === m}
                onClick={() => setViewMode(m)}
                style={{
                  padding: "6px 12px",
                  fontSize: 12,
                  fontWeight: 600,
                  borderRadius: "var(--radius-buttons)",
                  border:
                    viewMode === m
                      ? "1px solid var(--color-chartwell-blue)"
                      : "1px solid transparent",
                  background: viewMode === m ? "var(--color-sky-tint)" : "transparent",
                  color: "var(--color-slate-text)",
                  cursor: "pointer",
                  textTransform: "capitalize",
                }}
              >
                {m}
              </button>
            ))}
          </div>
          {sortedRuns.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-8)" }}>
              {viewMode === "cards" && (
                <button
                  type="button"
                  disabled={bulkRerunSubmitting || selectedTickers.size === 0}
                  onClick={() => void onBulkRerunSelected()}
                  title={
                    selectedTickers.size === 0
                      ? "Tick one or more ticker cards to enable bulk re-run"
                      : "Submit a batch of re-runs for the selected tickers"
                  }
                  style={{
                    padding: "8px 14px",
                    borderRadius: "var(--radius-buttons)",
                    border: "none",
                    background:
                      bulkRerunSubmitting || selectedTickers.size === 0
                        ? "var(--color-platinum-outline)"
                        : "var(--color-chartwell-blue)",
                    color: "white",
                    fontWeight: 600,
                    fontSize: "var(--text-caption)",
                    cursor:
                      bulkRerunSubmitting || selectedTickers.size === 0 ? "not-allowed" : "pointer",
                  }}
                >
                  {bulkRerunSubmitting
                    ? "Submitting…"
                    : `▶ Re-run selected (${selectedTickers.size})`}
                </button>
              )}
              <button
                type="button"
                disabled={bulkDeleting || selectedRunIds.size === 0}
                onClick={() => void onDeleteSelected()}
                style={{
                  padding: "8px 14px",
                  borderRadius: "var(--radius-buttons)",
                  border: "1px solid #fecaca",
                  background: selectedRunIds.size === 0 ? "#f3f4f6" : "#fff1f2",
                  color: "#991b1b",
                  fontWeight: 600,
                  fontSize: "var(--text-caption)",
                  cursor:
                    bulkDeleting || selectedRunIds.size === 0 ? "not-allowed" : "pointer",
                }}
              >
                {bulkDeleting ? "Deleting…" : `Delete selected (${selectedRunIds.size})`}
              </button>
              <button
                type="button"
                disabled={bulkDeleting}
                onClick={() => void onDeleteAllMatchingFilters()}
                style={{
                  padding: "8px 14px",
                  borderRadius: "var(--radius-buttons)",
                  border: "1px solid #fecaca",
                  background: "#fff1f2",
                  color: "#991b1b",
                  fontWeight: 600,
                  fontSize: "var(--text-caption)",
                  cursor: bulkDeleting ? "not-allowed" : "pointer",
                }}
              >
                Delete all matching filters
              </button>
            </div>
          )}
        </div>
        <p className="reading-callout" style={{ margin: "0 0 var(--spacing-8)", maxWidth: "72ch" }}>
          Compare ratings only when <strong>Model</strong> and <strong>Sources</strong> match — different LLMs or
          single-vendor setups can shift outcomes more than the ticker thesis.
        </p>
        <p
          style={{
            margin: "0 0 var(--spacing-8)",
            fontSize: "var(--text-caption)",
            color: "var(--color-steel-gray)",
            lineHeight: 1.45,
          }}
        >
          <strong>View</strong> opens the run page for that row. Tickers link to the stock-level page.
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
        {sortedRuns.length === 0 && !loading ? (
          <p style={{ color: "var(--color-ash-gray)" }}>
            No runs yet. Start an analysis from the dashboard — in-progress jobs appear here automatically.
          </p>
        ) : viewMode === "cards" ? (
          <HistoryTickerCards
            rows={sortedRuns}
            selectedTickers={selectedTickers}
            onToggleTicker={toggleTickerSelection}
            onRerun={(roll) => void onCardRerun(roll)}
            onOpenLatest={onCardOpenLatest}
            rerunPending={rerunPendingTickers}
            rerunError={rerunError}
          />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="history-runs-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid var(--color-stone-border)" }}>
                  <th style={{ padding: "8px 6px", width: 36 }}>
                    <input
                      type="checkbox"
                      aria-label="Select all visible runs"
                      checked={allRunsSelected}
                      onChange={toggleSelectAllVisible}
                      disabled={bulkDeleting || sortedRuns.length === 0}
                    />
                  </th>
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
                  <th style={{ padding: "8px 6px" }} title="LLM provider and models used for this run">
                    Model
                  </th>
                  <th
                    style={{ padding: "8px 6px" }}
                    title="Data vendor pillars and analyst breadth — warnings when setup may bias the rating"
                  >
                    Sources
                  </th>
                  <th
                    style={{ padding: "8px 6px" }}
                    title="Mini bars: six 0–100 factor scores. Source priority is persisted run snapshot first; if unavailable, the UI uses a current facts-only ticker preview and labels it."
                  >
                    Factors
                  </th>
                  <th style={{ padding: "8px 6px" }}>Status</th>
                  <th
                    style={{ padding: "8px 6px" }}
                    title="Job start or completion time, shown in Hong Kong (HKT)"
                  >
                    Processing (HKT)
                  </th>
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
                {sortedRuns.map((r) => (
                  <tr
                    key={r.run_id}
                    style={{
                      borderBottom: "1px solid var(--color-platinum-outline)",
                      background: r.is_live_job ? "rgba(219, 234, 254, 0.25)" : undefined,
                    }}
                  >
                    <td style={{ padding: "8px 6px", verticalAlign: "middle" }}>
                      <input
                        type="checkbox"
                        aria-label={`Select run ${r.run_id}`}
                        checked={selectedRunIds.has(r.run_id)}
                        onChange={() => toggleRunSelection(r.run_id)}
                        disabled={bulkDeleting || r.job_status !== "completed"}
                        title={r.job_status !== "completed" ? "Only completed runs can be bulk-deleted" : undefined}
                      />
                    </td>
                    <td style={{ padding: "8px 6px" }} className="mono">
                      {r.run_id}
                    </td>
                    <td style={{ padding: "8px 6px" }}>
                      {r.ticker ? (
                        <Link
                          to={stocksPath(r.ticker)}
                          className="link-action"
                          title={`All runs for ${r.ticker}`}
                        >
                          {r.ticker}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td style={{ padding: "8px 6px" }}>{r.date}</td>
                    <td style={{ padding: "8px 6px" }}>{r.rating ?? "—"}</td>
                    <td style={{ padding: "8px 6px" }}>{pct(r.confidence ?? undefined)}</td>
                    <td
                      style={{ padding: "8px 6px", maxWidth: 160 }}
                      className="mono"
                      title={provenanceTitle(r.provenance)}
                    >
                      {formatLlmLabel(r.provenance)}
                    </td>
                    <td
                      style={{
                        padding: "8px 6px",
                        maxWidth: 180,
                        color: hasBiasWarning(r.provenance) ? "#b45309" : undefined,
                      }}
                      title={provenanceTitle(r.provenance)}
                    >
                      {formatSourcesLabel(r.provenance)}
                    </td>
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
                    <td style={{ padding: "8px 6px" }}>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "2px 8px",
                          borderRadius: 999,
                          fontSize: 11,
                          fontWeight: 600,
                          ...statusBadgeStyle(r.job_status),
                        }}
                      >
                        {statusLabel(r.job_status)}
                      </span>
                    </td>
                    <td style={{ padding: "8px 6px" }} className="mono" title={r.processing_at ?? undefined}>
                      {formatHistoryTimestampWithZone(r.processing_at)}
                    </td>
                    <td style={{ padding: "8px 6px", textAlign: "right", verticalAlign: "middle" }}>
                      <Link to={runsPath(r.run_id)} className="link-action" style={{ fontSize: 11, fontWeight: 600 }}>
                        {r.job_status === "completed" ? "Open run →" : "Open job →"}
                      </Link>
                    </td>
                    <td style={{ padding: "8px 6px", textAlign: "right", verticalAlign: "middle" }}>
                      <button
                        type="button"
                        aria-label={`Delete run ${r.run_id}`}
                        disabled={
                          deletingRunId === r.run_id ||
                          (r.job_status !== "completed" &&
                            r.job_status !== "failed" &&
                            r.job_status !== "cancelled")
                        }
                        title={r.job_status !== "completed" ? "Only completed runs can be deleted from history" : undefined}
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
                          disabled={r.job_status !== "completed"}
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
                          disabled={r.job_status !== "completed"}
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
              aria-label="Compare run A"
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
              aria-label="Compare run B"
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
