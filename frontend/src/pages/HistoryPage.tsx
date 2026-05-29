import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";
import { paths, runsPath, stocksPath } from "../navigation/routes";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  bulkDeleteHistoryRuns,
  deleteAllHistoryRuns,
  deleteHistoryRun,
  fetchHistoryRun,
  fetchHistoryRuns,
  getDimensionsByTicker,
  postHistoryCompare,
  submitAnalyze,
  submitBatch,
  type HistoryCompareResponse,
  type HistoryRunRef,
} from "../api";
import { HistoryRunsTable } from "../components/history/HistoryRunsTable";
import { HistoryTickerCards } from "../components/history/HistoryTickerCards";
import { PageFrame, PageHeader, Panel } from "../components/PageFrame";
import type { TickerRollup } from "../utils/historyRollup";
import {
  buildRerunAnalyzePayload,
  formatPriorRunLlmLabel,
  withLlmOverrides,
} from "../utils/historyRerun";
import { RerunSetupDialog } from "../components/RerunSetupDialog";
import { llmConfigToOverrides, type LlmConfig } from "../components/LlmPicker";
import { retryAllFailedRuns, retryFailedRun } from "../utils/failedJobRetry";
import {
  hasActiveHistoryRows,
  mergeHistoryAndJobs,
  sortHistoryRows,
  type HistorySortKey,
  type HistoryTableRow,
} from "../utils/historyDisplay";
import { DimensionsRadar } from "../components/dimensions/DimensionsRadar";
import type { StockDimensions } from "../dimensions-types";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import {
  useJobsRefresh,
  useJobsTrackerContext,
} from "../contexts/JobsTrackerContext";
import { useThumbDimensions } from "../hooks/useThumbDimensions";

import type { Components } from "react-markdown";
import { prepareReportMarkdown } from "../utils/reportMarkdown";

const REPORT_MD_COMPONENTS: Components = {
  table: ({ children, ...rest }) => (
    <div className="markdown-table-wrap">
      <table {...rest}>{children}</table>
    </div>
  ),
};

function pct(conf: number | null | undefined): string {
  if (conf == null || !Number.isFinite(conf)) return "—";
  return `${Math.round(conf * 100)}%`;
}

export function HistoryPage() {
  const navigate = useNavigate();
  const refreshJobsRibbon = useJobsRefresh();
  const { jobsSnapshot } = useJobsTrackerContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const urlRunHandled = useRef(false);
  useDocumentTitle("Runs");
  /** Rows deleted this session — hidden until a full history refresh. */
  const [hiddenRunIds, setHiddenRunIds] = useState<Set<string>>(() => new Set());
  const [historyRows, setHistoryRows] = useState<HistoryRunRef[]>([]);
  const [sortKey, setSortKey] = useState<HistorySortKey>(
    () => (searchParams.get("sort") as HistorySortKey | null) ?? "processing_desc",
  );
  const [includeLiveJobs, setIncludeLiveJobs] = useState(
    () => searchParams.get("live") !== "0",
  );
  const [overnightOnly, setOvernightOnly] = useState(
    () => searchParams.get("overnight") === "1",
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tickerFilter, setTickerFilter] = useState(() => searchParams.get("ticker") ?? "");
  const [dateFrom, setDateFrom] = useState(() => searchParams.get("from") ?? "");
  const [dateTo, setDateTo] = useState(() => searchParams.get("to") ?? "");
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

  const [viewMode, setViewMode] = useState<"cards" | "table">(
    () => (searchParams.get("view") === "table" ? "table" : "cards"),
  );
  const [selectedTickers, setSelectedTickers] = useState<Set<string>>(new Set());
  const [rerunPendingTickers, setRerunPendingTickers] = useState<Set<string>>(new Set());
  const [rerunError, setRerunError] = useState<string | null>(null);
  const [bulkRerunSubmitting, setBulkRerunSubmitting] = useState(false);
  const [rerunTarget, setRerunTarget] = useState<
    | { kind: "single"; runId: string; ticker: string }
    | { kind: "bulk"; tickers: string[] }
    | { kind: "bulk-runs"; runIds: string[] }
    | null
  >(null);
  const [rerunDialogDetail, setRerunDialogDetail] = useState<{
    snapshot?: Record<string, unknown>;
    date?: string | null;
    priorLlm?: string | null;
  } | null>(null);
  const [failedOnly, setFailedOnly] = useState(
    () => searchParams.get("failed") === "1",
  );
  const [bulkRetrySubmitting, setBulkRetrySubmitting] = useState(false);
  const [failedRetryRunId, setFailedRetryRunId] = useState<string | null>(null);
  const [retrySummary, setRetrySummary] = useState<string | null>(null);
  const [compareDims, setCompareDims] = useState<{
    a: StockDimensions | null;
    b: StockDimensions | null;
  }>({ a: null, b: null });

  const mergeFilters = useMemo(
    () => ({
      ticker: tickerFilter.trim() || undefined,
      dateFrom: dateFrom.trim() || undefined,
      dateTo: dateTo.trim() || undefined,
      trigger: overnightOnly ? "overnight" : undefined,
    }),
    [tickerFilter, dateFrom, dateTo, overnightOnly],
  );

  const runs = useMemo(() => {
    const merged = mergeHistoryAndJobs(
      historyRows,
      includeLiveJobs ? jobsSnapshot : [],
      mergeFilters,
    );
    if (!hiddenRunIds.size) return merged;
    return merged.filter((r) => !hiddenRunIds.has(r.run_id));
  }, [historyRows, jobsSnapshot, includeLiveJobs, mergeFilters, hiddenRunIds]);

  const thumbDims = useThumbDimensions(runs, viewMode === "table");

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
      const history = await fetchHistoryRuns({
        ticker: mergeFilters.ticker,
        limit: 100,
        date_from: mergeFilters.dateFrom,
        date_to: mergeFilters.dateTo,
      });
      setHistoryRows(history);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setHistoryRows([]);
    } finally {
      setLoading(false);
    }
  }, [mergeFilters]);

  const sortedRuns = useMemo(
    () => sortHistoryRows(runs, sortKey),
    [runs, sortKey],
  );

  const visibleRuns = useMemo(
    () => (failedOnly ? sortedRuns.filter((r) => r.job_status === "failed") : sortedRuns),
    [sortedRuns, failedOnly],
  );

  const failedCount = useMemo(
    () => sortedRuns.filter((r) => r.job_status === "failed").length,
    [sortedRuns],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Sync filters → URL so back/forward and reload preserve view.
  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    const setOrDel = (k: string, v: string | null) => {
      if (v && v.length) next.set(k, v);
      else next.delete(k);
    };
    setOrDel("ticker", tickerFilter.trim().toUpperCase() || null);
    setOrDel("from", dateFrom.trim() || null);
    setOrDel("to", dateTo.trim() || null);
    setOrDel("sort", sortKey === "processing_desc" ? null : sortKey);
    setOrDel("live", includeLiveJobs ? null : "0");
    setOrDel("overnight", overnightOnly ? "1" : null);
    setOrDel("failed", failedOnly ? "1" : null);
    setOrDel("view", viewMode === "cards" ? null : viewMode);
    if (next.toString() !== searchParams.toString()) {
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    tickerFilter,
    dateFrom,
    dateTo,
    sortKey,
    includeLiveJobs,
    overnightOnly,
    failedOnly,
    viewMode,
  ]);

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

  const liveCounts = useMemo(() => {
    let running = 0;
    let queued = 0;
    for (const r of sortedRuns) {
      if (r.job_status === "running") running += 1;
      else if (r.job_status === "queued") queued += 1;
    }
    return { running, queued };
  }, [sortedRuns]);

  function pruneAfterDeletes(deletedIds: string[]) {
    const gone = new Set(deletedIds);
    setHiddenRunIds((prev) => {
      const next = new Set(prev);
      deletedIds.forEach((id) => next.add(id));
      return next;
    });
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

  function openRerunDialog(runId: string, ticker: string) {
    setRerunError(null);
    setRerunDialogDetail(null);
    setRerunTarget({ kind: "single", runId, ticker });
    void fetchHistoryRun(runId)
      .then((detail) => {
        setRerunDialogDetail({
          snapshot: detail.config_snapshot,
          date: detail.date,
          priorLlm: formatPriorRunLlmLabel(detail.config_snapshot, detail.provenance),
        });
      })
      .catch(() => {
        setRerunDialogDetail({ priorLlm: null });
      });
  }

  function onCardRerun(rollup: TickerRollup) {
    const baseRun = rollup.latestCompletedRun;
    if (!baseRun) return;
    openRerunDialog(baseRun.run_id, rollup.ticker);
  }

  function onTableRerun(row: HistoryTableRow) {
    if (row.job_status !== "completed") return;
    const ticker = (row.ticker ?? "").trim().toUpperCase() || "?";
    openRerunDialog(row.run_id, ticker);
  }

  const selectedCompletedRunIds = useMemo(
    () =>
      [...selectedRunIds].filter((id) => {
        const row = sortedRuns.find((r) => r.run_id === id);
        return row?.job_status === "completed";
      }),
    [selectedRunIds, sortedRuns],
  );

  function onBulkRerunSelectedRuns() {
    if (!selectedCompletedRunIds.length) return;
    setRerunError(null);
    setRerunDialogDetail(null);
    setRerunTarget({ kind: "bulk-runs", runIds: selectedCompletedRunIds });
  }

  async function onConfirmRerun(llm: LlmConfig) {
    if (!rerunTarget) return;
    setRerunError(null);

    if (rerunTarget.kind === "bulk-runs") {
      setBulkRerunSubmitting(true);
      const errors: string[] = [];
      let lastJobId: string | null = null;
      try {
        for (const runId of rerunTarget.runIds) {
          try {
            const detail = await fetchHistoryRun(runId);
            const body = withLlmOverrides(buildRerunAnalyzePayload(detail), llm);
            const r = await submitAnalyze(body);
            lastJobId = r.job_id;
          } catch (e: unknown) {
            errors.push(
              `${runId}: ${e instanceof Error ? e.message : String(e)}`,
            );
          }
        }
        refreshJobsRibbon();
        setSelectedRunIds(new Set());
        setRerunTarget(null);
        if (errors.length) {
          setRerunError(errors.slice(0, 3).join(" · "));
        }
        if (lastJobId) navigate(runsPath(lastJobId));
      } finally {
        setBulkRerunSubmitting(false);
      }
      return;
    }

    if (rerunTarget.kind === "bulk") {
      setBulkRerunSubmitting(true);
      try {
        const r = await submitBatch({
          tickers: rerunTarget.tickers,
          config_overrides: llmConfigToOverrides(llm),
        });
        refreshJobsRibbon();
        setSelectedTickers(new Set());
        setRerunTarget(null);
        navigate(`/batch?id=${encodeURIComponent(r.batch_id)}`);
      } catch (e: unknown) {
        setRerunError(e instanceof Error ? e.message : String(e));
      } finally {
        setBulkRerunSubmitting(false);
      }
      return;
    }

    const { runId, ticker } = rerunTarget;
    setRerunPendingTickers((prev) => new Set(prev).add(ticker));
    try {
      const detailPayload = await fetchHistoryRun(runId);
      const body = withLlmOverrides(buildRerunAnalyzePayload(detailPayload), llm);
      const r = await submitAnalyze(body);
      refreshJobsRibbon();
      setRerunTarget(null);
      navigate(runsPath(r.job_id));
    } catch (e: unknown) {
      setRerunError(e instanceof Error ? e.message : String(e));
    } finally {
      setRerunPendingTickers((prev) => {
        const next = new Set(prev);
        next.delete(ticker);
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

  async function onRetryOneFailed(row: HistoryTableRow) {
    setRerunError(null);
    setRetrySummary(null);
    setFailedRetryRunId(row.run_id);
    try {
      const result = await retryFailedRun(row);
      await refresh();
      navigate(runsPath(result.action === "resumed" ? result.jobId : result.newJobId));
    } catch (e: unknown) {
      setRerunError(e instanceof Error ? e.message : String(e));
    } finally {
      setFailedRetryRunId(null);
    }
  }

  async function onRetryAllFailed() {
    const failed = sortedRuns.filter((r) => r.job_status === "failed");
    if (!failed.length) return;
    if (
      !window.confirm(
        `Retry ${failed.length} failed job${failed.length === 1 ? "" : "s"}? ` +
          "Jobs with checkpoints resume where they left off; others start fresh with the same ticker and settings.",
      )
    ) {
      return;
    }
    setRerunError(null);
    setRetrySummary(null);
    setBulkRetrySubmitting(true);
    try {
      const summary = await retryAllFailedRuns(failed);
      const parts = [
        summary.resumed ? `${summary.resumed} resumed` : null,
        summary.submitted ? `${summary.submitted} restarted` : null,
        summary.errors.length ? `${summary.errors.length} error(s)` : null,
      ].filter(Boolean);
      setRetrySummary(parts.join(", ") || "Done");
      if (summary.errors.length === 1) {
        setRerunError(`${summary.errors[0].jobId}: ${summary.errors[0].message}`);
      } else if (summary.errors.length > 1) {
        setRerunError(
          summary.errors.slice(0, 3).map((e) => `${e.jobId}: ${e.message}`).join(" · "),
        );
      }
      await refresh();
    } catch (e: unknown) {
      setRerunError(e instanceof Error ? e.message : String(e));
    } finally {
      setBulkRetrySubmitting(false);
    }
  }

  function onBulkRerunSelected() {
    const tickers = [...selectedTickers].filter(Boolean);
    if (!tickers.length) return;
    setRerunError(null);
    setRerunDialogDetail(null);
    setRerunTarget({ kind: "bulk", tickers });
  }



  const runA = runSelectOptions.find((o) => o.id === runIdA.trim());
  const runB = runSelectOptions.find((o) => o.id === runIdB.trim());

  return (
    <PageFrame className="history-page" wide>
      <PageHeader
        title="Runs & compare"
        description="Completed runs and live jobs in one list. Times in Hong Kong (HKT). Click column headers to sort; use A/B on a row or the compare panel below."
        meta={
          <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-16)", flexWrap: "wrap" }}>
            <AppBreadcrumbs items={[{ label: "Runs" }]} />
            <Link to={paths.historyStats} className="ui-link" style={{ fontSize: "var(--text-caption)" }}>
              View rating statistics →
            </Link>
          </div>
        }
      />

      <Panel title="Filters">
        <div className="history-page__filters">
          <label className="history-page__field">
            <span className="history-page__field-label">Ticker</span>
            <input
              value={tickerFilter}
              onChange={(e) => setTickerFilter(e.target.value)}
              placeholder="e.g. AAPL"
            />
          </label>
          <label className="history-page__field">
            <span className="history-page__field-label">From</span>
            <input
              type="text"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              placeholder="YYYY-MM-DD"
              className="mono"
            />
          </label>
          <label className="history-page__field">
            <span className="history-page__field-label">To</span>
            <input
              type="text"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              placeholder="YYYY-MM-DD"
              className="mono"
            />
          </label>
          <label className="history-page__field history-page__field--wide">
            <span className="history-page__field-label">Sort preset</span>
            <select
              aria-label="Sort history runs"
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as HistorySortKey)}
            >
              <option value="processing_desc">Processing (newest)</option>
              <option value="processing_asc">Processing (oldest)</option>
              <option value="status_desc">Status (active first)</option>
              <option value="status_asc">Status (completed first)</option>
              <option value="trade_date_desc">Trade date (newest)</option>
              <option value="trade_date_asc">Trade date (oldest)</option>
              <option value="ticker_asc">Ticker (A→Z)</option>
              <option value="ticker_desc">Ticker (Z→A)</option>
              <option value="rating_desc">Rating (bullish first)</option>
              <option value="rating_asc">Rating (bearish first)</option>
              <option value="confidence_desc">Confidence (high)</option>
              <option value="confidence_asc">Confidence (low)</option>
            </select>
          </label>
          <label className="history-page__toggle">
            <input
              type="checkbox"
              checked={includeLiveJobs}
              onChange={(e) => setIncludeLiveJobs(e.target.checked)}
            />
            Include in-progress jobs
          </label>
          <label className="history-page__toggle">
            <input
              type="checkbox"
              checked={overnightOnly}
              onChange={(e) => setOvernightOnly(e.target.checked)}
            />
            Overnight / scan triggers only
          </label>
          <label className="history-page__toggle">
            <input
              type="checkbox"
              checked={failedOnly}
              onChange={(e) => setFailedOnly(e.target.checked)}
            />
            Failed only
          </label>
          <button
            type="button"
            className="ui-btn-primary"
            onClick={() => void refresh()}
            disabled={loading}
          >
            {loading ? "Loading…" : "Apply"}
          </button>
        </div>
        {error && <p className="panel__error">{error}</p>}
        {deleteError && <p className="panel__error">{deleteError}</p>}
      </Panel>

      <Panel>
        <div className="history-page__toolbar">
          <div className="history-page__toolbar-title">
            <h2 className="panel__title" style={{ margin: 0 }}>
              Recent runs ({visibleRuns.length}
              {failedOnly && sortedRuns.length !== visibleRuns.length
                ? ` of ${sortedRuns.length}`
                : ""}
              )
            </h2>
            {(liveCounts.running > 0 || liveCounts.queued > 0) && (
              <div className="history-page__count-badges">
                {liveCounts.running > 0 && (
                  <span className="history-page__count-badge history-page__count-badge--live">
                    {liveCounts.running} running
                  </span>
                )}
                {liveCounts.queued > 0 && (
                  <span className="history-page__count-badge">
                    {liveCounts.queued} queued
                  </span>
                )}
              </div>
            )}
          </div>
          <div
            className="history-page__view-toggle"
            role="tablist"
            aria-label="Recent runs view mode"
          >
            {(["cards", "table"] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="tab"
                aria-selected={viewMode === m}
                onClick={() => setViewMode(m)}
              >
                {m}
              </button>
            ))}
          </div>
          {sortedRuns.length > 0 && (
            <div className="history-page__bulk-actions">
              {failedCount > 0 && (
                <button
                  type="button"
                  className="ui-btn-secondary"
                  disabled={bulkRetrySubmitting || bulkRerunSubmitting}
                  onClick={() => void onRetryAllFailed()}
                >
                  {bulkRetrySubmitting
                    ? "Retrying…"
                    : `Retry failed (${failedCount})`}
                </button>
              )}
              {viewMode === "cards" && (
                <button
                  type="button"
                  className="ui-btn-primary"
                  disabled={bulkRerunSubmitting || selectedTickers.size === 0}
                  onClick={() => void onBulkRerunSelected()}
                  title="Batch re-run latest completed run per selected ticker"
                >
                  {bulkRerunSubmitting
                    ? "Submitting…"
                    : `Re-run tickers (${selectedTickers.size})`}
                </button>
              )}
              {viewMode === "table" && (
                <button
                  type="button"
                  className="ui-btn-primary"
                  disabled={
                    bulkRerunSubmitting || selectedCompletedRunIds.length === 0
                  }
                  onClick={() => onBulkRerunSelectedRuns()}
                  title="Re-run each selected completed run with its stored date and analysts"
                >
                  {bulkRerunSubmitting
                    ? "Submitting…"
                    : `Re-run runs (${selectedCompletedRunIds.length})`}
                </button>
              )}
              <button
                type="button"
                className="ui-btn-danger"
                disabled={bulkDeleting || selectedRunIds.size === 0}
                onClick={() => void onDeleteSelected()}
              >
                {bulkDeleting ? "Deleting…" : `Delete (${selectedRunIds.size})`}
              </button>
              <button
                type="button"
                className="ui-btn-ghost"
                disabled={bulkDeleting}
                onClick={() => void onDeleteAllMatchingFilters()}
              >
                Delete all matching
              </button>
            </div>
          )}
        </div>

        <p className="reading-callout">
          Compare ratings only when <strong>Model</strong> and <strong>Sources</strong> match.
        </p>

        <details className="history-page__guide">
          <summary>How to read this table</summary>
          <div className="history-page__guide-body">
            <p>
              <strong>Confidence</strong> follows the final rating tier, not statistical certainty.
              <strong> Factors</strong> use each run&apos;s persisted snapshot when available; otherwise a live facts-only preview (labeled <em>live</em>).
            </p>
            <p>
              Peer comparison is market-local first, then sector-wide, then a legacy global bucket.
              Warm caches with{" "}
              <code>scripts/warm_peer_cache.py global|local|sector</code>.
            </p>
          </div>
        </details>

        {rerunError && <p className="panel__error">{rerunError}</p>}
        {retrySummary && !rerunError && (
          <p className="panel__hint" role="status">
            Retry complete: {retrySummary}.
          </p>
        )}

        {visibleRuns.length === 0 && !loading ? (
          <p className="panel__empty">
            {failedOnly ? "No failed runs in the current filter." : "No runs yet. Start an analysis from the dashboard."}
          </p>
        ) : viewMode === "cards" ? (
          <HistoryTickerCards
            rows={visibleRuns}
            selectedTickers={selectedTickers}
            onToggleTicker={toggleTickerSelection}
            onRerun={(roll) => void onCardRerun(roll)}
            onOpenLatest={onCardOpenLatest}
            rerunPending={rerunPendingTickers}
            rerunError={rerunError}
          />
        ) : (
          <HistoryRunsTable
            rows={visibleRuns}
            sortKey={sortKey}
            onSortKeyChange={setSortKey}
            thumbDims={thumbDims}
            selectedRunIds={selectedRunIds}
            allRunsSelected={allRunsSelected}
            onToggleSelectAll={toggleSelectAllVisible}
            onToggleRunSelection={toggleRunSelection}
            bulkDeleting={bulkDeleting}
            deletingRunId={deletingRunId}
            onDeleteRun={(id) => void onDeleteRun(id)}
            runIdA={runIdA}
            runIdB={runIdB}
            onSelectCompareA={(id) => {
              setRunIdA(id);
              setCompareError(null);
            }}
            onSelectCompareB={(id) => {
              setRunIdB(id);
              setCompareError(null);
            }}
            onRetryFailed={(row) => void onRetryOneFailed(row)}
            retryingRunId={failedRetryRunId}
            onRerunRun={onTableRerun}
            rerunPendingRunId={
              rerunTarget?.kind === "single" ? rerunTarget.runId : null
            }
          />
        )}
      </Panel>

      <Panel
        title="Compare two runs"
        subtitle="Pick A/B on any completed row, or use the dropdowns. Model and sources should match for a fair read."
      >
        <div className="history-page__compare-picks">
          <span>Side A</span>
          <span
            className={`history-page__compare-chip${runA ? " history-page__compare-chip--filled" : ""}`}
          >
            {runA?.label ?? "Not selected"}
          </span>
          <span>Side B</span>
          <span
            className={`history-page__compare-chip${runB ? " history-page__compare-chip--filled" : ""}`}
          >
            {runB?.label ?? "Not selected"}
          </span>
        </div>
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
      </Panel>
      <RerunSetupDialog
        open={rerunTarget != null}
        title={
          rerunTarget?.kind === "bulk"
            ? "Batch re-run (tickers)"
            : rerunTarget?.kind === "bulk-runs"
              ? "Re-run selected runs"
              : "Re-run analysis"
        }
        description={
          rerunTarget?.kind === "bulk"
            ? `Choose models for ${rerunTarget.tickers.length} ticker${rerunTarget.tickers.length === 1 ? "" : "s"}. Dates and analysts follow each ticker’s latest completed run; batch submits tickers only.`
            : rerunTarget?.kind === "bulk-runs"
              ? `Choose models for ${rerunTarget.runIds.length} run${rerunTarget.runIds.length === 1 ? "" : "s"}. Each run keeps its own ticker, trade date, and analyst set.`
              : "Choose LLM provider and models for this run. Ticker, date, and analysts stay the same as the previous completed run."
        }
        runSummary={
          rerunTarget?.kind === "single"
            ? `${rerunTarget.ticker}${rerunDialogDetail?.date ? ` · ${rerunDialogDetail.date}` : ""}`
            : rerunTarget?.kind === "bulk"
              ? rerunTarget.tickers.join(", ")
              : rerunTarget?.kind === "bulk-runs"
                ? `${rerunTarget.runIds.length} selected run${rerunTarget.runIds.length === 1 ? "" : "s"}`
                : null
        }
        priorRunLlm={rerunDialogDetail?.priorLlm ?? null}
        configSnapshot={rerunDialogDetail?.snapshot ?? null}
        submitting={
          rerunTarget?.kind === "bulk" || rerunTarget?.kind === "bulk-runs"
            ? bulkRerunSubmitting
            : rerunTarget?.kind === "single"
              ? rerunPendingTickers.has(rerunTarget.ticker)
              : false
        }
        confirmLabel={
          rerunTarget?.kind === "bulk"
            ? "Start batch"
            : rerunTarget?.kind === "bulk-runs"
              ? "Start runs"
              : "Start run"
        }
        onClose={() => {
          if (bulkRerunSubmitting) return;
          if (rerunTarget?.kind === "single" && rerunPendingTickers.has(rerunTarget.ticker)) {
            return;
          }
          setRerunTarget(null);
        }}
        onConfirm={onConfirmRerun}
      />
    </PageFrame>
  );
}
