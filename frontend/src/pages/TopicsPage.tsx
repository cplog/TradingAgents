import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Link } from "react-router-dom";
import { PageFrame, PageHeader, Panel } from "../components/PageFrame";
import { TopicCard } from "../components/topics/TopicCard";
import { CadenceSelect } from "../components/topics/CadenceSelect";
import { useTopics } from "../hooks/useTopics";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { fetchHpmScore, type HPMScoreResult, type TopicCadence } from "../api";
import { topicPath } from "../navigation/routes";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";

const staggerContainer = {
  initial: {},
  animate: { transition: { staggerChildren: 0.06, delayChildren: 0.04 } },
};

export function TopicsPage() {
  const { pinned, trending, loading, refreshing, error, searching, search, togglePin } = useTopics();
  const initialLoad = loading && pinned.length === 0 && trending.length === 0;
  const [query, setQuery] = useState("");
  const [cadence, setCadence] = useState<TopicCadence>("daily");
  const [hpmScore, setHpmScore] = useState<HPMScoreResult | null>(null);
  useDocumentTitle("Topics");

  useEffect(() => {
    fetchHpmScore().then(setHpmScore).catch(console.error);
  }, []);

  async function onSearch(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    await search(q, cadence);
    setQuery("");
  }

  return (
    <PageFrame className="content-entrance">
      <PageHeader
        title="Hot Ideas (Topics)"
        description="Discover investment themes via web research. Extract tickers and send them to Batch analysis."
        meta={<AppBreadcrumbs items={[{ label: "Topics" }]} />}
      />

      {hpmScore ? (
        <div className="regime-banner">
          <div className="regime-banner__header">
            <strong>Market Regime: {hpmScore.trading_posture.replace(/_/g, " ")}</strong>
            {" "}— Score: {hpmScore.composite_score.toFixed(1)}/5.0, Confidence: {Math.round(hpmScore.regime_confidence * 100)}%
            <span className="regime-banner__timestamp">
              Updated {new Date(hpmScore.timestamp).toLocaleTimeString()}
            </span>
          </div>

          <div className="regime-banner__signals">
            {Object.entries(hpmScore.signals).map(([name, sig]) => (
              <div key={name} className="regime-banner__signal-row">
                <span className="regime-banner__signal-name">
                  {name.replace(/_/g, " ")}
                </span>
                <span className="regime-banner__signal-bar">
                  <span
                    className="regime-banner__signal-fill"
                    style={{ width: `${sig.score * 100}%` }}
                  />
                </span>
                <span className="regime-banner__signal-score">
                  {sig.score.toFixed(2)}
                </span>
                <span
                  className={`regime-banner__signal-direction regime-banner__signal-direction--${sig.direction}`}
                >
                  {sig.direction === "up" ? "↑" : sig.direction === "down" ? "↓" : "→"}
                </span>
              </div>
            ))}
          </div>

          {hpmScore.dominant_transmission_chain.length > 0 && (
            <div className="regime-banner__footnote">
              <strong>Transmission:</strong>{" "}
              {hpmScore.dominant_transmission_chain.join(" → ")}
            </div>
          )}

          {hpmScore.regime_reason_codes.length > 0 && (
            <div className="regime-banner__footnote">
              <strong>Evidence:</strong>{" "}
              {hpmScore.regime_reason_codes.map((c) => c.replace(/_/g, " ")).join("; ")}
            </div>
          )}
        </div>
      ) : null}

      <Panel title="Search a theme">
        <form className="ui-form-row ui-form-row--stretch" onSubmit={(e) => void onSearch(e)}>
          <input
            className="ui-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. nuclear SMR utilities uranium"
            aria-label="Theme search query"
          />
          <CadenceSelect value={cadence} onChange={setCadence} />
          <button type="submit" className="ui-btn ui-btn--primary" disabled={searching}>
            {searching ? "Searching…" : "Search & run"}
          </button>
        </form>
      </Panel>

      {error ? <p className="ui-error">{error}</p> : null}
      {initialLoad ? <p>Loading topics…</p> : null}
      {refreshing ? (
        <p className="topics-refresh-hint" aria-live="polite">
          Updating…
        </p>
      ) : null}

      {!initialLoad && pinned.length > 0 ? (
        <section className="topics-section">
          <h2 className="topics-section__title">Pinned</h2>
          <motion.div
            initial="initial"
            animate="animate"
            variants={staggerContainer}
            className="topics-grid"
          >
            {pinned.map((t) => (
              <TopicCard key={t.id} topic={t} onPinToggle={togglePin} />
            ))}
          </motion.div>
        </section>
      ) : null}

      <section className="topics-section">
        <h2 className="topics-section__title">{pinned.length ? "Trending" : "All topics"}</h2>
        {trending.length === 0 && !initialLoad ? (
          <p className="topics-empty">No topics yet. Search above or wait for seed themes to load.</p>
        ) : (
          <motion.div
            initial="initial"
            animate="animate"
            variants={staggerContainer}
            className="topics-grid"
          >
            {trending.map((t) => (
              <TopicCard key={t.id} topic={t} onPinToggle={togglePin} />
            ))}
          </motion.div>
        )}
      </section>

      <p className="page-lead">
        Tip: open a topic for articles and candidates, then{" "}
        <Link to={topicPath("ai-infrastructure")}>batch analyze</Link> extracted tickers.
      </p>
    </PageFrame>
  );
}
