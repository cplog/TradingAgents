import { Link } from "react-router-dom";
import type { TickerCandidate } from "../../api";
import { paths } from "../../navigation/routes";
import { MarketBadge } from "./MarketBadge";

function formatPrice(v: number | null | undefined): string {
  if (v == null) return "";
  return `$${v.toFixed(2)}`;
}

function formatMarketCap(v: number | null | undefined): string {
  if (v == null) return "";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toLocaleString()}`;
}

type Props = {
  candidate: TickerCandidate;
  onAddWatchlist?: (ticker: string) => void;
};

export function TickerCandidateRow({ candidate, onAddWatchlist }: Props) {
  const pct = Math.round(candidate.confidence * 100);
  const positive = candidate.change_pct != null && candidate.change_pct >= 0;
  return (
    <div className="topics-candidate-row">
      <div className="topics-candidate-row__main">
        <Link to={`${paths.batch}?tickers=${encodeURIComponent(candidate.ticker)}`} className="topics-candidate-row__ticker">
          {candidate.ticker}
        </Link>
        <MarketBadge market={candidate.market} />
        {candidate.company_name ? (
          <span className="topics-candidate-row__name">{candidate.company_name}</span>
        ) : null}
      </div>

      <div className="topics-candidate-row__metrics">
        {candidate.price != null ? (
          <span className="topics-candidate-row__metric" title="Price">
            {formatPrice(candidate.price)}
          </span>
        ) : null}
        {candidate.change_pct != null ? (
          <span
            className="topics-candidate-row__metric"
            data-change={positive ? "up" : "down"}
            title="Change %"
          >
            {positive ? "+" : ""}{candidate.change_pct.toFixed(1)}%
          </span>
        ) : null}
        {candidate.market_cap != null ? (
          <span className="topics-candidate-row__metric topics-candidate-row__metric--muted" title="Market cap">
            {formatMarketCap(candidate.market_cap)}
          </span>
        ) : null}
        {candidate.sector ? (
          <span className="topics-candidate-row__metric topics-candidate-row__metric--muted" title="Sector">
            {candidate.sector}
          </span>
        ) : null}
      </div>

      <div className="topics-candidate-row__meta">
        <span 
          className="topics-candidate-row__confidence" 
          title={
            candidate.base_confidence != null
              ? `Base: ${Math.round(candidate.base_confidence * 100)}% × Style: ${candidate.style_multiplier} × Regime Conf: ${Math.round((candidate.regime_confidence || 1) * 100)}% = ${pct}%`
              : "Calibrated confidence"
          }
        >
          {pct}% conf
        </span>
        {candidate.rationale ? (
          <p className="topics-candidate-row__rationale">{candidate.rationale}</p>
        ) : null}
      </div>

      {onAddWatchlist ? (
        <button
          type="button"
          className="ui-btn ui-btn--ghost"
          onClick={() => onAddWatchlist(candidate.ticker)}
        >
          + Browser watchlist
        </button>
      ) : null}
    </div>
  );
}
