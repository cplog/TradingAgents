import { useAutoAnimate } from "@formkit/auto-animate/react";
import { Link } from "react-router-dom";
import { runsPath, stocksPath } from "../../navigation/routes";
import { FactorBar } from "../dimensions/FactorBar";
import type { FactorScores, StockDimensions } from "../../dimensions-types";
import {
  formatHistoryTimestampWithZone,
  ratingTone,
  shortenRunId,
  sortDirectionForColumn,
  sortKeyForColumn,
  statusLabel,
  type HistorySortKey,
  type HistorySortableColumn,
  type HistoryTableRow,
} from "../../utils/historyDisplay";
import {
  formatLlmLabel,
  formatSourcesLabel,
  hasBiasWarning,
  provenanceTitle,
} from "../../utils/runProvenance";
import { HistoryStatusBadge } from "./HistoryStatusBadge";

const FACTOR_KEYS: (keyof FactorScores)[] = [
  "value",
  "growth",
  "quality",
  "momentum",
  "low_risk",
  "sentiment",
];

type RowFactorSource = "run_snapshot" | "live_preview" | "loading" | "unavailable";

function pct(conf: number | null | undefined): string {
  if (conf == null || !Number.isFinite(conf)) return "—";
  return `${Math.round(conf * 100)}%`;
}

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

function factorSourceLabel(source: RowFactorSource): string {
  if (source === "run_snapshot") return "run";
  if (source === "live_preview") return "live";
  if (source === "loading") return "loading";
  return "n/a";
}

function SortableTh({
  column,
  label,
  sortKey,
  onSort,
  title,
}: {
  column: HistorySortableColumn;
  label: string;
  sortKey: HistorySortKey;
  onSort: (key: HistorySortKey) => void;
  title?: string;
}) {
  const dir = sortDirectionForColumn(column, sortKey);
  return (
    <th scope="col">
      <button
        type="button"
        className={`history-runs-table__sort${dir ? ` history-runs-table__sort--${dir}` : ""}`}
        onClick={() => onSort(sortKeyForColumn(column, sortKey))}
        title={title ?? `Sort by ${label}`}
        aria-sort={dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none"}
      >
        <span>{label}</span>
        <span className="history-runs-table__sort-icon" aria-hidden />
      </button>
    </th>
  );
}

export type HistoryRunsTableProps = {
  rows: HistoryTableRow[];
  sortKey: HistorySortKey;
  onSortKeyChange: (key: HistorySortKey) => void;
  thumbDims: Record<string, StockDimensions | null>;
  selectedRunIds: Set<string>;
  allRunsSelected: boolean;
  onToggleSelectAll: () => void;
  onToggleRunSelection: (runId: string) => void;
  bulkDeleting: boolean;
  deletingRunId: string | null;
  onDeleteRun: (runId: string) => void;
  runIdA: string;
  runIdB: string;
  onSelectCompareA: (runId: string) => void;
  onSelectCompareB: (runId: string) => void;
  onRetryFailed?: (row: HistoryTableRow) => void;
  retryingRunId?: string | null;
};

export function HistoryRunsTable({
  rows,
  sortKey,
  onSortKeyChange,
  thumbDims,
  selectedRunIds,
  allRunsSelected,
  onToggleSelectAll,
  onToggleRunSelection,
  bulkDeleting,
  deletingRunId,
  onDeleteRun,
  runIdA,
  runIdB,
  onSelectCompareA,
  onSelectCompareB,
  onRetryFailed,
  retryingRunId = null,
}: HistoryRunsTableProps) {
  const [bodyRef] = useAutoAnimate();

  return (
    <div className="history-runs-table-wrap">
      <table className="history-runs-table">
        <thead>
          <tr>
            <th scope="col" className="history-runs-table__col-check">
              <input
                type="checkbox"
                aria-label="Select all visible runs"
                checked={allRunsSelected}
                onChange={onToggleSelectAll}
                disabled={bulkDeleting || rows.length === 0}
              />
            </th>
            <th scope="col" className="history-runs-table__col-id">
              Run
            </th>
            <SortableTh
              column="ticker"
              label="Ticker"
              sortKey={sortKey}
              onSort={onSortKeyChange}
            />
            <SortableTh column="date" label="Date" sortKey={sortKey} onSort={onSortKeyChange} />
            <SortableTh
              column="rating"
              label="Rating"
              sortKey={sortKey}
              onSort={onSortKeyChange}
            />
            <th
              scope="col"
              title="Heuristic from final rating tier, not model uncertainty"
            >
              Conf.
            </th>
            <th scope="col">Model</th>
            <th scope="col">Sources</th>
            <th
              scope="col"
              title="Six factor scores; run snapshot preferred, else live preview"
            >
              Factors
            </th>
            <SortableTh
              column="status"
              label="Status"
              sortKey={sortKey}
              onSort={onSortKeyChange}
            />
            <SortableTh
              column="processing"
              label="Processed (HKT)"
              sortKey={sortKey}
              onSort={onSortKeyChange}
              title="Job start or completion time in Hong Kong"
            />
            <th scope="col" className="history-runs-table__col-actions">
              Actions
            </th>
          </tr>
        </thead>
        <tbody ref={bodyRef}>
          {rows.map((r) => {
            const factorSource = inferRowFactorSource(
              r,
              r.ticker ? thumbDims[r.ticker] : null,
            );
            const canDelete =
              r.job_status === "completed" ||
              r.job_status === "failed" ||
              r.job_status === "cancelled";
            const canBulkSelect = canDelete;
            return (
              <tr
                key={r.run_id}
                className={r.is_live_job ? "history-runs-table__row--live" : undefined}
                data-status={r.job_status}
              >
                <td className="history-runs-table__col-check">
                  <input
                    type="checkbox"
                    aria-label={`Select run ${r.run_id}`}
                    checked={selectedRunIds.has(r.run_id)}
                    onChange={() => onToggleRunSelection(r.run_id)}
                    disabled={bulkDeleting || !canBulkSelect}
                    title={
                      !canBulkSelect
                        ? "Only completed, failed, or cancelled runs can be bulk-deleted"
                        : undefined
                    }
                  />
                </td>
                <td className="history-runs-table__col-id mono" title={r.run_id}>
                  {shortenRunId(r.run_id)}
                </td>
                <td>
                  {r.ticker ? (
                    <Link
                      to={stocksPath(r.ticker)}
                      className="history-runs-table__ticker"
                      title={`All runs for ${r.ticker}`}
                    >
                      {r.ticker}
                    </Link>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="mono">{r.date ?? "—"}</td>
                <td>
                  <span className={`rating-cell rating-cell--${ratingTone(r.rating)}`}>
                    {r.rating ?? "—"}
                  </span>
                </td>
                <td className="mono">{pct(r.confidence ?? undefined)}</td>
                <td className="mono history-runs-table__col-meta" title={provenanceTitle(r.provenance)}>
                  {formatLlmLabel(r.provenance)}
                </td>
                <td
                  className={`history-runs-table__col-meta${hasBiasWarning(r.provenance) ? " history-runs-table__col-warn" : ""}`}
                  title={provenanceTitle(r.provenance)}
                >
                  {formatSourcesLabel(r.provenance)}
                </td>
                <td>
                  <div className="history-runs-table__factors">
                    {FACTOR_KEYS.map((k) => (
                      <FactorBar
                        key={k}
                        label=""
                        score={pickRowFactorScore(r, r.ticker ? thumbDims[r.ticker] : null, k)}
                        width={36}
                      />
                    ))}
                    <span
                      className={`meta-tag meta-tag--${factorSource === "run_snapshot" ? "run" : factorSource === "live_preview" ? "live" : "muted"}`}
                      title={
                        factorSource === "run_snapshot"
                          ? "Persisted factor snapshot from this run"
                          : factorSource === "live_preview"
                            ? "Live facts-only preview (no run snapshot)"
                            : factorSource === "loading"
                              ? "Loading preview"
                              : "No factors available"
                      }
                    >
                      {factorSourceLabel(factorSource)}
                    </span>
                  </div>
                </td>
                <td>
                  <HistoryStatusBadge status={r.job_status} />
                </td>
                <td className="mono" title={r.processing_at ?? undefined}>
                  {formatHistoryTimestampWithZone(r.processing_at)}
                </td>
                <td className="history-runs-table__col-actions">
                  <div className="history-runs-table__actions">
                    {r.job_status === "failed" && onRetryFailed ? (
                      <button
                        type="button"
                        className="ui-btn-secondary"
                        style={{ fontSize: "var(--text-ui-sm)", padding: "2px 8px" }}
                        disabled={retryingRunId === r.run_id}
                        title={
                          r.resumable
                            ? "Resume from LangGraph checkpoint"
                            : "Start a new analysis with the same ticker and settings"
                        }
                        onClick={() => onRetryFailed(r)}
                      >
                        {retryingRunId === r.run_id ? "…" : "Retry"}
                      </button>
                    ) : null}
                    <Link
                      to={runsPath(r.run_id)}
                      className="ui-btn-ghost ui-btn-ghost--sm"
                    >
                      {r.job_status === "completed" ? "Open" : "Job"}
                    </Link>
                    <button
                      type="button"
                      className="ui-btn-ghost ui-btn-ghost--sm history-runs-table__compare-btn"
                      data-selected={runIdA === r.run_id ? "a" : runIdB === r.run_id ? "b" : undefined}
                      aria-label={`Compare A: ${r.ticker ?? r.run_id}`}
                      disabled={r.job_status !== "completed"}
                      onClick={() => onSelectCompareA(r.run_id)}
                    >
                      A
                    </button>
                    <button
                      type="button"
                      className="ui-btn-ghost ui-btn-ghost--sm history-runs-table__compare-btn"
                      data-selected={runIdB === r.run_id ? "b" : undefined}
                      aria-label={`Compare B: ${r.ticker ?? r.run_id}`}
                      disabled={r.job_status !== "completed"}
                      onClick={() => onSelectCompareB(r.run_id)}
                    >
                      B
                    </button>
                    <button
                      type="button"
                      className="ui-btn-ghost ui-btn-ghost--sm history-runs-table__delete-btn"
                      aria-label={`Delete run ${r.run_id}`}
                      disabled={deletingRunId === r.run_id || !canDelete}
                      title={
                        !canDelete
                          ? `Only terminal runs can be deleted (${statusLabel(r.job_status)})`
                          : "Delete from history"
                      }
                      onClick={() => {
                        if (!window.confirm(`Delete run ${r.run_id}? This cannot be undone.`)) {
                          return;
                        }
                        onDeleteRun(r.run_id);
                      }}
                    >
                      {deletingRunId === r.run_id ? "…" : "Del"}
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
