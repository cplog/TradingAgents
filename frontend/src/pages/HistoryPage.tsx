import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";
import { paths, runsPath, stocksPath } from "../navigation/routes";
import {
  bulkDeleteHistoryRuns,
  deleteAllHistoryRuns,
  deleteHistoryRun,
  fetchHistoryRun,
  fetchHistoryRuns,
  postHistoryCompare,
  submitAnalyze,
  type HistoryCompareResponse,
  type HistoryRunRef,
} from "../api";
import { HistoryRunsTable } from "../components/history/HistoryRunsTable";
import { RunComparisonResults } from "../components/history/RunComparisonResults";
import { PageFrame, PageHeader, Panel } from "../components/PageFrame";
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
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import {
  useJobsRefresh,
  useJobsTrackerContext,
} from "../contexts/JobsTrackerContext";
import { useThumbDimensions } from "../hooks/useThumbDimensions";

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
  const [runIdA, setRunIdA] = useState(() => searchParams.get("compareA") ?? "");
  const [runIdB, setRunIdB] = useState(() => searchParams.get("compareB") ?? "");
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [compare, setCompare] = useState<HistoryCompareResponse | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletingRunId, setDeletingRunId] = useState<string | null>(null);
  const [selectedRunIds, setSelectedRunIds] = useState<Set<string>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [showFullPm, setShowFullPm] = useState(false);
  const compareResultsRef = useRef<HTMLElement | null>(null);

  const viewMode = "table" as const;
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

  // Auto-run compare when both IDs are present in URL on first load
  const compareInitiated = useRef(false);
  useEffect(() => {
    if (compareInitiated.current) return;
    const ca = searchParams.get("compareA")?.trim();
    const cb = searchParams.get("compareB")?.trim();
    if (ca && cb && ca !== cb && !compare && !compareLoading) {
      compareInitiated.current = true;
      void onCompare();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

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
    setOrDel("compareA", runIdA.trim() || null);
    setOrDel("compareB", runIdB.trim() || null);
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
    runIdA,
    runIdB,
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

  const runA = runSelectOptions.find((o) => o.id === runIdA.trim());
  const runB = runSelectOptions.find((o) => o.id === runIdB.trim());
  const compareDockOpen =
    runSelectOptions.length >= 2 ||
    Boolean(runIdA.trim() || runIdB.trim() || compare || compareError);
  const hasBulkSelection = selectedRunIds.size > 0;

  function clearCompareSelection() {
    setRunIdA("");
    setRunIdB("");
    setCompare(null);
    setCompareError(null);
  }

  return (
        <PageFrame className="history-page content-entrance" wide>
      <PageHeader
        title="Runs"
        description="Past analyses and live jobs. Times in HKT."
        meta={
          <div className="history-page__header-meta">
            <AppBreadcrumbs items={[{ label: "Runs" }]} />
            <Link to={paths.historyStats} className="ui-link history-page__stats-link">
              Rating statistics
            </Link>
          </div>
        }
      />

      <Panel>
        <div className="history-page__control-bar">
          <div className="history-page__filters">
            <label className="history-page__field">
              <span className="history-page__field-label">Ticker</span>
              <input
                value={tickerFilter}
                onChange={(e) => setTickerFilter(e.target.value)}
                placeholder="AAPL"
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

            <button
              type="button"
              className="ui-btn-ghost history-page__refresh"
              onClick={() => void refresh()}
              disabled={loading}
              title="Refresh list"
              aria-label="Refresh runs"
            >
              {loading ? "…" : "↻"}
            </button>
          </div>

          <details className="history-page__advanced">
            <summary>More filters</summary>
            <div className="history-page__advanced-body">
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
            </div>
          </details>
        </div>

        {error && <p className="panel__error">{error}</p>}
        {deleteError && <p className="panel__error">{deleteError}</p>}

        <div className="history-page__toolbar">
          <div className="history-page__toolbar-title">
            <h2 className="panel__title history-page__list-title">
              {visibleRuns.length} run{visibleRuns.length === 1 ? "" : "s"}
              {failedOnly && sortedRuns.length !== visibleRuns.length
                ? ` · ${sortedRuns.length} total`
                : ""}
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
          {failedCount > 0 && (
            <button
              type="button"
              className="ui-btn-secondary"
              disabled={bulkRetrySubmitting || bulkRerunSubmitting}
              onClick={() => void onRetryAllFailed()}
            >
              {bulkRetrySubmitting ? "Retrying…" : `Retry failed (${failedCount})`}
            </button>
          )}
        </div>

        {hasBulkSelection && (
          <div className="history-page__selection-bar" role="toolbar" aria-label="Bulk actions">
            <span className="history-page__selection-count">
              {selectedRunIds.size} run{selectedRunIds.size === 1 ? "" : "s"} selected
            </span>
            <div className="history-page__bulk-actions">
              <button
                type="button"
                className="ui-btn-primary"
                disabled={bulkRerunSubmitting || selectedCompletedRunIds.length === 0}
                onClick={() => onBulkRerunSelectedRuns()}
              >
                {bulkRerunSubmitting
                  ? "Submitting…"
                  : `Re-run (${selectedCompletedRunIds.length})`}
              </button>
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
          </div>
        )}

        <details className="history-page__guide">
          <summary>Column guide</summary>
          <div className="history-page__guide-body">
            <p>
              <strong>Confidence</strong> follows the final rating tier, not statistical certainty.
              <strong> Factors</strong> use each run&apos;s persisted snapshot when available; otherwise a live preview (labeled <em>live</em>).
            </p>
            <p>
              Compare ratings only when <strong>Model</strong> and <strong>Sources</strong> match.
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
          <div className="history-page__empty">
            <p className="panel__empty">
              {failedOnly
                ? "No failed runs match these filters."
                : "No runs yet."}
            </p>
            {!failedOnly && (
              <Link to={paths.dashboard} className="ui-btn-primary history-page__empty-cta">
                Start analysis
              </Link>
            )}
          </div>
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

        <AnimatePresence>
          {compareDockOpen && (
            <motion.div
              key="compare-dock"
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0, transition: { duration: 0.22, ease: [0.25, 1, 0.5, 1] } }}
              exit={{ opacity: 0, y: -8, transition: { duration: 0.15, ease: [0.25, 1, 0.5, 1] } }}
              className="history-page__compare-dock"
              aria-label="Compare runs"
            >
            <div className="history-page__compare-dock-head">
              <span className="history-page__compare-dock-label">Compare</span>
              <span
                className={`history-page__compare-chip${runA ? " history-page__compare-chip--filled" : ""}`}
                title={runA?.label}
              >
                {runA ? `${runA.label.split(" · ")[0]} · ${runA.label.split(" · ")[1] ?? runA.id}` : "Pick A"}
              </span>
              <span className="history-page__compare-vs">vs</span>
              <span
                className={`history-page__compare-chip${runB ? " history-page__compare-chip--filled" : ""}`}
                title={runB?.label}
              >
                {runB ? `${runB.label.split(" · ")[0]} · ${runB.label.split(" · ")[1] ?? runB.id}` : "Pick B"}
              </span>
            </div>
            <div className="history-page__compare-dock-controls">
              <label className="history-page__compare-select">
                <select
                  aria-label="Compare run A"
                  value={runIdA}
                  onChange={(e) => {
                    setRunIdA(e.target.value);
                    setCompareError(null);
                  }}
                >
                  <option value="">Run A…</option>
                  {runSelectOptions.map((o) => (
                    <option key={`a-${o.id}`} value={o.id}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="history-page__compare-select">
                <select
                  aria-label="Compare run B"
                  value={runIdB}
                  onChange={(e) => {
                    setRunIdB(e.target.value);
                    setCompareError(null);
                  }}
                >
                  <option value="">Run B…</option>
                  {runSelectOptions.map((o) => (
                    <option key={`b-${o.id}`} value={o.id}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="ui-btn-primary"
                disabled={compareLoading || !compareReady}
                onClick={() => void onCompare()}
                title={
                  !compareReady
                    ? "Select two different completed runs"
                    : "Load side-by-side comparison"
                }
              >
                {compareLoading ? "Comparing…" : "Compare"}
              </button>
              <button
                type="button"
                className="ui-btn-secondary"
                disabled={compareLoading || !runIdA.trim() || !runIdB.trim()}
                onClick={() => {
                  const ta = runIdA;
                  setRunIdA(runIdB);
                  setRunIdB(ta);
                  setCompare(null);
                }}
              >
                Swap
              </button>
              <button
                type="button"
                className="ui-btn-ghost"
                onClick={clearCompareSelection}
              >
                Clear
              </button>
            </div>
            <p className="history-page__compare-hint">
              Click <strong>A</strong>/<strong>B</strong> on a row, or use the dropdowns.{" "}
              Match model and sources for a fair read.
            </p>
            {compareError && <p className="panel__error">{compareError}</p>}
          </motion.div>
        )}
        </AnimatePresence>

        <AnimatePresence>
          {compare && (
            <motion.div
              ref={compareResultsRef}
              className="history-page__compare-results"
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.2, ease: [0.25, 1, 0.5, 1] }}
            >
              <header className="history-page__compare-results-head">
                <div>
                  <p className="history-page__compare-results-kicker">Comparison</p>
                  <h3 className="history-page__compare-results-title">
                    {compare.a.ticker && compare.b.ticker && compare.a.ticker.toUpperCase() === compare.b.ticker.toUpperCase()
                      ? `${compare.a.ticker} · ${compare.a.date ?? ''} vs ${compare.b.date ?? ''}`
                      : `${compare.a.ticker ?? 'A'} vs ${compare.b.ticker ?? 'B'}`}
                  </h3>
                </div>
              </header>
              <RunComparisonResults
                compare={compare}
                showFullPm={showFullPm}
                onToggleFullPm={() => setShowFullPm((v) => !v)}
              />
            </motion.div>
          )}
        </AnimatePresence>
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
