import { useMemo, type CSSProperties } from "react";
import type { HistoryTableRow } from "../../utils/historyDisplay";
import { groupRunsByTicker, relativeFromNow, type TickerRollup } from "../../utils/historyRollup";
import { statusLabel } from "../../utils/historyDisplay";

type Props = {
  rows: HistoryTableRow[];
  selectedTickers: Set<string>;
  onToggleTicker(ticker: string): void;
  onRerun(rollup: TickerRollup): void;
  onOpenLatest(rollup: TickerRollup): void;
  /** Set of tickers whose Re-run button is currently pending an API call. */
  rerunPending: Set<string>;
  /** Optional error to surface near the action area, e.g. submitAnalyze failure. */
  rerunError: string | null;
};

function ratingTone(rating: string | null | undefined): { bg: string; fg: string; border: string } {
  const r = (rating ?? "").trim();
  switch (r) {
    case "Buy":
    case "Overweight":
      return {
        bg: "rgba(120, 240, 168, 0.16)",
        fg: "var(--color-phosphor)",
        border: "1px solid rgba(120, 240, 168, 0.45)",
      };
    case "Sell":
    case "Underweight":
      return {
        bg: "rgba(248, 113, 113, 0.14)",
        fg: "#f87171",
        border: "1px solid rgba(248, 113, 113, 0.45)",
      };
    case "Hold":
      return {
        bg: "rgba(245, 158, 11, 0.14)",
        fg: "var(--color-amber-readout, #f59e0b)",
        border: "1px solid rgba(245, 158, 11, 0.45)",
      };
    default:
      return {
        bg: "var(--surface-canvas-fog)",
        fg: "var(--color-ash-gray)",
        border: "1px solid var(--color-stone-border)",
      };
  }
}

function activeBadgeStyle(): CSSProperties {
  return {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: "2px 8px",
    borderRadius: 999,
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: "0.02em",
    background: "rgba(120, 240, 168, 0.14)",
    color: "var(--color-phosphor)",
    border: "1px solid rgba(120, 240, 168, 0.4)",
  };
}

export function HistoryTickerCards({
  rows,
  selectedTickers,
  onToggleTicker,
  onRerun,
  onOpenLatest,
  rerunPending,
  rerunError,
}: Props) {
  const rollups = useMemo(() => groupRunsByTicker(rows), [rows]);

  if (!rollups.length) {
    return (
      <p style={{ margin: 0, color: "var(--color-ash-gray)" }}>
        No tickers in view. Adjust filters or start an analysis from the dashboard.
      </p>
    );
  }

  return (
    <div className="history-ticker-cards" style={{ display: "grid", gap: "var(--spacing-12)" }}>
      {rerunError && (
        <div role="alert" style={{ fontSize: "var(--text-caption)", color: "#f87171" }}>
          {rerunError}
        </div>
      )}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 18rem), 1fr))",
          gap: "var(--spacing-16)",
        }}
      >
        {rollups.map((roll) => {
          const tone = ratingTone(roll.latestCompletedRun?.rating ?? roll.latestRun.rating);
          const isSelected = selectedTickers.has(roll.ticker);
          const canRerun = Boolean(roll.latestCompletedRun) && !rerunPending.has(roll.ticker);
          const latestRunRow = roll.latestCompletedRun ?? roll.latestRun;
          const latestId = latestRunRow.job_id ?? latestRunRow.run_id;
          return (
            <article
              key={roll.ticker}
              className="history-ticker-card"
              data-ticker={roll.ticker}
              aria-selected={isSelected}
              style={{
                position: "relative",
                display: "grid",
                gap: "var(--spacing-12)",
                padding: "var(--spacing-16)",
                borderRadius: "var(--radius-cards)",
                border: isSelected
                  ? "1px solid var(--color-chartwell-blue, var(--color-phosphor))"
                  : "1px solid var(--color-stone-border)",
                background: "var(--surface-cloud-white)",
                boxShadow: isSelected
                  ? "0 0 0 2px rgba(120, 240, 168, 0.18)"
                  : "var(--shadow-subtle)",
                minWidth: 0,
              }}
            >
              <header
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  justifyContent: "space-between",
                  gap: "var(--spacing-8)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => onToggleTicker(roll.ticker)}
                    aria-label={`Select ticker ${roll.ticker} for bulk actions`}
                    disabled={!roll.latestCompletedRun}
                    title={
                      roll.latestCompletedRun
                        ? "Include in bulk re-run"
                        : "No completed runs to re-run for this ticker"
                    }
                    style={{ marginTop: 2 }}
                  />
                  <div style={{ display: "grid", gap: 2, minWidth: 0 }}>
                    <div
                      className="mono"
                      style={{
                        fontSize: "var(--text-heading-sm)",
                        fontWeight: 700,
                        color: "var(--color-slate-text)",
                        letterSpacing: "0.01em",
                      }}
                    >
                      {roll.ticker}
                    </div>
                    <div
                      style={{
                        fontSize: 11,
                        color: "var(--color-ash-gray)",
                      }}
                    >
                      {roll.runCount} run{roll.runCount === 1 ? "" : "s"}
                      {roll.completedRunCount !== roll.runCount && (
                        <> · {roll.completedRunCount} completed</>
                      )}
                    </div>
                  </div>
                </div>
                <span
                  className="history-ticker-card__rating"
                  style={{
                    display: "inline-flex",
                    padding: "4px 10px",
                    borderRadius: 999,
                    fontSize: 12,
                    fontWeight: 700,
                    background: tone.bg,
                    color: tone.fg,
                    border: tone.border,
                    whiteSpace: "nowrap",
                  }}
                  title={roll.latestCompletedRun ? "Latest persisted rating" : "Latest known rating"}
                >
                  {roll.latestCompletedRun?.rating ?? roll.latestRun.rating ?? "—"}
                </span>
              </header>

              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "var(--spacing-8)",
                  fontSize: 12,
                  color: "var(--color-steel-gray)",
                }}
              >
                <span title={latestRunRow.processing_at ?? undefined}>
                  Last: <strong style={{ color: "var(--color-slate-text)" }}>
                    {relativeFromNow(latestRunRow.processing_at)}
                  </strong>
                </span>
                {latestRunRow.date && <span>· as of {latestRunRow.date}</span>}
                {roll.activeStatus && (
                  <span style={activeBadgeStyle()}>
                    <span
                      aria-hidden
                      style={{
                        display: "inline-block",
                        width: 6,
                        height: 6,
                        borderRadius: 999,
                        background: "var(--color-phosphor)",
                      }}
                    />
                    {statusLabel(roll.activeStatus)}
                  </span>
                )}
              </div>

              <div
                className="mono"
                style={{
                  fontSize: 11,
                  color: "var(--color-ash-gray)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={`Latest run id: ${latestRunRow.run_id}`}
              >
                Latest run · {latestRunRow.run_id}
              </div>

              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "var(--spacing-8)",
                  marginTop: "auto",
                }}
              >
                <button
                  type="button"
                  onClick={() => onRerun(roll)}
                  disabled={!canRerun}
                  title={
                    !roll.latestCompletedRun
                      ? "No completed run to re-run yet"
                      : "Re-run with the same ticker, date, and analysts — choose models in the dialog"
                  }
                  style={{
                    padding: "8px 14px",
                    fontSize: 12,
                    fontWeight: 600,
                    borderRadius: "var(--radius-buttons)",
                    border: "none",
                    background: canRerun ? "var(--color-chartwell-blue)" : "var(--color-platinum-outline)",
                    color: "white",
                    cursor: canRerun ? "pointer" : "not-allowed",
                  }}
                >
                  {rerunPending.has(roll.ticker) ? "Submitting…" : "▶ Re-run"}
                </button>
                <button
                  type="button"
                  onClick={() => onOpenLatest(roll)}
                  disabled={!latestId}
                  title="Open the most recent run in detail view"
                  style={{
                    padding: "8px 14px",
                    fontSize: 12,
                    fontWeight: 600,
                    borderRadius: "var(--radius-buttons)",
                    border: "1px solid var(--color-stone-border)",
                    background: "var(--surface-canvas-fog)",
                    color: "var(--color-slate-text)",
                    cursor: latestId ? "pointer" : "not-allowed",
                  }}
                >
                  → Open latest
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
