import { memo, useMemo, type CSSProperties } from "react";
import type { HistoryTableRow } from "../../utils/historyDisplay";
import { groupRunsByTicker, relativeFromNow, type TickerRollup } from "../../utils/historyRollup";
import { statusLabel } from "../../utils/historyDisplay";

type Props = {
  rows: HistoryTableRow[];
  selectedTickers: Set<string>;
  onToggleTicker(ticker: string): void;
  onRerun(rollup: TickerRollup): void;
  onOpenLatest(rollup: TickerRollup): void;
  rerunPending: Set<string>;
  rerunError: string | null;
};

const TONE_MAP: Record<string, { bg: string; fg: string; border: string }> = {
  Buy:        { bg: "rgba(232, 140, 77, 0.16)", fg: "var(--color-phosphor)",           border: "1px solid rgba(232, 140, 77, 0.45)" },
  Overweight: { bg: "rgba(232, 140, 77, 0.16)", fg: "var(--color-phosphor)",           border: "1px solid rgba(232, 140, 77, 0.45)" },
  Sell:       { bg: "rgba(196, 123, 94, 0.14)", fg: "var(--color-danger)",             border: "1px solid rgba(196, 123, 94, 0.45)" },
  Underweight:{ bg: "rgba(196, 123, 94, 0.14)", fg: "var(--color-danger)",             border: "1px solid rgba(196, 123, 94, 0.45)" },
  Hold:       { bg: "rgba(183, 131, 59, 0.14)", fg: "var(--color-warning)",            border: "1px solid rgba(183, 131, 59, 0.45)" },
};

function ratingTone(rating: string | null | undefined) {
  return TONE_MAP[(rating ?? "").trim()] ?? {
    bg: "var(--surface-canvas-fog)",
    fg: "var(--color-ash-gray)",
    border: "1px solid var(--color-stone-border)",
  };
}

// --- Module-level static style constants (created once) ---
const EMPTY_STYLE: CSSProperties = { margin: 0, color: "var(--color-ash-gray)" };
const CONTAINER_STYLE: CSSProperties = { display: "grid", gap: "var(--spacing-12)" };
const GRID_STYLE: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 18rem), 1fr))",
  gap: "var(--spacing-16)",
};
const ERROR_STYLE: CSSProperties = { fontSize: "var(--text-caption)", color: "var(--color-danger)" };
const HEADER_STYLE: CSSProperties = {
  display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "var(--spacing-8)",
};
const CHECKBOX_WRAPPER_STYLE: CSSProperties = { display: "flex", alignItems: "center", gap: 8, minWidth: 0 };
const CHECKBOX_STYLE: CSSProperties = { marginTop: 2 };
const TICKER_NAME_STYLE: CSSProperties = {
  fontSize: "var(--text-heading-sm)", fontWeight: 700, color: "var(--color-slate-text)", letterSpacing: "0.01em",
};
const RUN_COUNT_STYLE: CSSProperties = { fontSize: 11, color: "var(--color-ash-gray)" };
const META_ROW_STYLE: CSSProperties = {
  display: "flex", flexWrap: "wrap", gap: "var(--spacing-8)", fontSize: 12, color: "var(--color-steel-gray)",
};
const STRONG_STYLE: CSSProperties = { color: "var(--color-slate-text)" };
const ACTIVE_DOT_STYLE: CSSProperties = {
  display: "inline-block", width: 6, height: 6, borderRadius: 999, background: "var(--color-phosphor)",
};
const RUN_ID_STYLE: CSSProperties = {
  fontSize: 11, color: "var(--color-ash-gray)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
};
const BUTTON_ROW_STYLE: CSSProperties = {
  display: "flex", flexWrap: "wrap", gap: "var(--spacing-8)", marginTop: "auto",
};

function activeBadgeStyle(): CSSProperties {
  return {
    display: "inline-flex", alignItems: "center", gap: 6, padding: "2px 8px",
    borderRadius: 999, fontSize: 11, fontWeight: 600, letterSpacing: "0.02em",
    background: "rgba(232, 140, 77, 0.14)", color: "var(--color-phosphor)",
    border: "1px solid rgba(232, 140, 77, 0.4)",
  };
}

function cardStyle(isSelected: boolean): CSSProperties {
  return {
    position: "relative", display: "grid", gap: "var(--spacing-12)",
    padding: "var(--spacing-16)", borderRadius: "var(--radius-cards)",
    border: isSelected
      ? "1px solid var(--color-chartwell-blue, var(--color-phosphor))"
      : "1px solid var(--color-stone-border)",
    background: "var(--surface-cloud-white)",
    boxShadow: isSelected ? "0 0 0 2px rgba(232, 140, 77, 0.18)" : "var(--shadow-subtle)",
    minWidth: 0,
  };
}

function ratingBadgeStyle(tone: ReturnType<typeof ratingTone>): CSSProperties {
  return {
    display: "inline-flex", padding: "4px 10px", borderRadius: 999, fontSize: 12,
    fontWeight: 700, background: tone.bg, color: tone.fg, border: tone.border, whiteSpace: "nowrap",
  };
}

function rerunBtnStyle(canRerun: boolean): CSSProperties {
  return {
    padding: "8px 14px", fontSize: 12, fontWeight: 600, borderRadius: "var(--radius-buttons)",
    border: "none",
    background: canRerun ? "var(--color-chartwell-blue)" : "var(--color-platinum-outline)",
    color: "var(--surface-canvas-fog)", cursor: canRerun ? "pointer" : "not-allowed",
  };
}

const OPEN_LATEST_STYLE: CSSProperties = {
  padding: "8px 14px", fontSize: 12, fontWeight: 600, borderRadius: "var(--radius-buttons)",
  border: "1px solid var(--color-stone-border)", background: "var(--surface-canvas-fog)",
  color: "var(--color-slate-text)",
};

export const HistoryTickerCards = memo(function HistoryTickerCards({
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
    return <p style={EMPTY_STYLE}>No tickers in view. Adjust filters or start an analysis from the dashboard.</p>;
  }

  return (
    <div className="history-ticker-cards" style={CONTAINER_STYLE}>
      {rerunError && <div role="alert" style={ERROR_STYLE}>{rerunError}</div>}
      <div className="history-ticker-cards__grid" style={GRID_STYLE}>
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
              style={cardStyle(isSelected)}
            >
              <header style={HEADER_STYLE}>
                <div style={CHECKBOX_WRAPPER_STYLE}>
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
                    style={CHECKBOX_STYLE}
                  />
                  <div style={{ display: "grid", gap: 2, minWidth: 0 }}>
                    <div className="mono" style={TICKER_NAME_STYLE}>{roll.ticker}</div>
                    <div style={RUN_COUNT_STYLE}>
                      {roll.runCount} run{roll.runCount === 1 ? "" : "s"}
                      {roll.completedRunCount !== roll.runCount && <> · {roll.completedRunCount} completed</>}
                    </div>
                  </div>
                </div>
                <span
                  className="history-ticker-card__rating"
                  style={ratingBadgeStyle(tone)}
                  title={roll.latestCompletedRun ? "Latest persisted rating" : "Latest known rating"}
                >
                  {roll.latestCompletedRun?.rating ?? roll.latestRun.rating ?? "—"}
                </span>
              </header>

              <div style={META_ROW_STYLE}>
                <span title={latestRunRow.processing_at ?? undefined}>
                  Last: <strong style={STRONG_STYLE}>{relativeFromNow(latestRunRow.processing_at)}</strong>
                </span>
                {latestRunRow.date && <span>· as of {latestRunRow.date}</span>}
                {roll.activeStatus && (
                  <span style={activeBadgeStyle()}>
                    <span aria-hidden style={ACTIVE_DOT_STYLE} />
                    {statusLabel(roll.activeStatus)}
                  </span>
                )}
              </div>

              <div className="mono" style={RUN_ID_STYLE} title={`Latest run id: ${latestRunRow.run_id}`}>
                Latest run · {latestRunRow.run_id}
              </div>

              <div style={BUTTON_ROW_STYLE}>
                <button
                  type="button"
                  onClick={() => onRerun(roll)}
                  disabled={!canRerun}
                  title={
                    !roll.latestCompletedRun
                      ? "No completed run to re-run yet"
                      : "Re-run with the same ticker, date, and analysts. Choose models in the dialog."
                  }
                  style={rerunBtnStyle(canRerun)}
                >
                  {rerunPending.has(roll.ticker) ? "Submitting…" : "\u25B6 Re-run"}
                </button>
                <button
                  type="button"
                  onClick={() => onOpenLatest(roll)}
                  disabled={!latestId}
                  title="Open the most recent run in detail view"
                  style={{
                    ...OPEN_LATEST_STYLE,
                    cursor: latestId ? "pointer" : "not-allowed",
                  }}
                >
                  {"\u2192 Open latest"}
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
});
