import type { JobLiveContext } from "../utils/livePlanContext";
import { formatLivePrice, isInvalidatedStatus } from "../utils/livePlanContext";

type Props = {
  context: JobLiveContext;
  tradeDate?: string | null;
  loading?: boolean;
  error?: string | null;
};

function statusLabel(status: string): string {
  switch (status) {
    case "below_stop":
      return "Setup invalidated";
    case "below_entry":
      return "Below entry zone";
    case "in_entry_zone":
      return "Near entry zone";
    case "above_entry":
      return "Above entry";
    case "above_target":
      return "At/above target";
    case "quote_unavailable":
      return "Live quote unavailable";
    case "no_levels":
      return "No plan levels";
    default:
      return "Live vs plan";
  }
}

function statusClass(status: string): string {
  if (status === "below_stop") return "live-vs-plan--invalidated";
  if (status === "below_entry" || status === "quote_unavailable" || status === "no_levels") {
    return "live-vs-plan--caution";
  }
  if (status === "in_entry_zone") return "live-vs-plan--ok";
  return "live-vs-plan--neutral";
}

export function LiveVsPlanStrip({ context, tradeDate, loading, error }: Props) {
  const { quote, comparison, report_close, levels, run_time_quote } = context;
  const tone = statusClass(comparison.status);
  const suggestRefresh = comparison.suggest_refresh === true;

  return (
    <section
      className={`live-vs-plan ${tone}`}
      aria-label="Live price versus report plan"
      aria-live="polite"
    >
      <div className="live-vs-plan__head">
        <span className="live-vs-plan__badge">{statusLabel(comparison.status)}</span>
        {loading ? <span className="live-vs-plan__meta">Refreshing quote…</span> : null}
        {error ? <span className="live-vs-plan__meta live-vs-plan__meta--error">{error}</span> : null}
      </div>

      <dl className="live-vs-plan__grid">
        <div>
          <dt>Live now</dt>
          <dd className="mono">{formatLivePrice(quote.price, quote.currency)}</dd>
        </div>
        {run_time_quote?.price != null ? (
          <div>
            <dt>At run time</dt>
            <dd className="mono">
              {formatLivePrice(run_time_quote.price, run_time_quote.currency ?? quote.currency)}
            </dd>
          </div>
        ) : null}
        {tradeDate && report_close != null ? (
          <div>
            <dt>Report date close</dt>
            <dd className="mono">
              {formatLivePrice(report_close, quote.currency)} · {tradeDate}
            </dd>
          </div>
        ) : tradeDate ? (
          <div>
            <dt>Report as of</dt>
            <dd>{tradeDate}</dd>
          </div>
        ) : null}
        {levels.entry != null ? (
          <div>
            <dt>Planned entry</dt>
            <dd className="mono">{levels.entry.toLocaleString(undefined, { maximumFractionDigits: 2 })}</dd>
          </div>
        ) : null}
        {levels.stop_loss != null ? (
          <div>
            <dt>Stop</dt>
            <dd className="mono">{levels.stop_loss.toLocaleString(undefined, { maximumFractionDigits: 2 })}</dd>
          </div>
        ) : null}
        {levels.price_target != null ? (
          <div>
            <dt>Target</dt>
            <dd className="mono">{levels.price_target.toLocaleString(undefined, { maximumFractionDigits: 2 })}</dd>
          </div>
        ) : null}
      </dl>

      <p className="live-vs-plan__guidance">{comparison.guidance}</p>

      {isInvalidatedStatus(comparison.status) ? (
        <p className="live-vs-plan__historical">
          Historical rating unchanged. This warning reflects <strong>current price vs this run&apos;s levels</strong>.
          {suggestRefresh
            ? " Refresh analysis with today\u2019s date before acting."
            : " Analysis already used the live quote at run time; do not use these levels as-is."}
        </p>
      ) : context.historical_rating_note ? (
        <p className="live-vs-plan__historical">{context.historical_rating_note}</p>
      ) : null}
    </section>
  );
}
