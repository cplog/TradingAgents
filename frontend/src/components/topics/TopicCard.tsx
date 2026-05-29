import { Link } from "react-router-dom";
import type { TopicSummary } from "../../api";
import { topicPath } from "../../navigation/routes";
import { MarketBadge } from "./MarketBadge";

type Props = {
  topic: TopicSummary;
  onPinToggle?: (id: string, pinned: boolean) => void;
};

export function TopicCard({ topic, onPinToggle }: Props) {
  return (
    <article className="topics-card">
      <header className="topics-card__header">
        <Link to={topicPath(topic.id)} className="topics-card__title">
          {topic.label}
        </Link>
        {onPinToggle ? (
          <button
            type="button"
            className={`topics-card__pin${topic.pinned ? " topics-card__pin--active" : ""}`}
            aria-label={topic.pinned ? "Unpin topic" : "Pin topic"}
            onClick={() => onPinToggle(topic.id, topic.pinned)}
          >
            {topic.pinned ? "Pinned" : "Pin"}
          </button>
        ) : null}
      </header>
      <p className="topics-card__query">{topic.query}</p>
      <div className="topics-card__meta">
        <span>{topic.cadence}</span>
        {topic.last_run_at ? (
          <span>Updated {new Date(topic.last_run_at).toLocaleString()}</span>
        ) : (
          <span>Not run yet</span>
        )}
        <span>{topic.candidate_count} tickers</span>
      </div>
      {topic.top_candidates.length > 0 ? (
        <ul className="topics-card__candidates">
          {topic.top_candidates.slice(0, 3).map((c) => (
            <li key={c.ticker}>
              <span className="mono">{c.ticker}</span>
              <MarketBadge market={c.market} />
              <span>{Math.round(c.confidence * 100)}%</span>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}
