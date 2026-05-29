import { Link } from "react-router-dom";
import type { TickerCandidate } from "../../api";
import { paths } from "../../navigation/routes";
import { MarketBadge } from "./MarketBadge";

type Props = {
  candidate: TickerCandidate;
  onAddWatchlist?: (ticker: string) => void;
};

export function TickerCandidateRow({ candidate, onAddWatchlist }: Props) {
  const pct = Math.round(candidate.confidence * 100);
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
      <div className="topics-candidate-row__meta">
        <span className="topics-candidate-row__confidence" title="Calibrated confidence">
          {pct}%
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
