import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { PageFrame, PageHeader, Panel } from "../components/PageFrame";
import { ArticleList } from "../components/topics/ArticleList";
import { CadenceSelect } from "../components/topics/CadenceSelect";
import { ThemeSummary } from "../components/topics/ThemeSummary";
import { TickerCandidateRow } from "../components/topics/TickerCandidateRow";
import { useTopicDetail } from "../hooks/useTopicDetail";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { paths } from "../navigation/routes";
import type { TopicCadence } from "../api";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";

const WATCHLIST_KEY = "ta:watchlist";

function addToWatchlist(ticker: string) {
  try {
    const raw = globalThis.localStorage?.getItem(WATCHLIST_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    const list = Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
    const sym = ticker.trim().toUpperCase();
    if (!list.includes(sym)) {
      list.push(sym);
      globalThis.localStorage?.setItem(WATCHLIST_KEY, JSON.stringify(list));
    }
  } catch {
    /* ignore */
  }
}

export function TopicDetailPage() {
  const { topicId = "" } = useParams();
  const navigate = useNavigate();
  const { topic, latestRun, runs, loading, refreshing, error, refresh, patch, togglePin, remove } =
    useTopicDetail(topicId);

  const [editLabel, setEditLabel] = useState("");
  const [editQuery, setEditQuery] = useState("");
  const [editCadence, setEditCadence] = useState<TopicCadence>("daily");
  const [editing, setEditing] = useState(false);
  useDocumentTitle(topic ? `${topic.label} · Topic` : "Topic");

  const candidates = latestRun?.candidates ?? [];
  const articles = latestRun?.articles ?? [];

  const batchUrl = useMemo(() => {
    const tickers = candidates.map((c) => c.ticker).join(", ");
    if (!tickers) return paths.batch;
    return `${paths.batch}?tickers=${encodeURIComponent(tickers)}&topic=${encodeURIComponent(topicId)}`;
  }, [candidates, topicId]);

  function startEdit() {
    if (!topic) return;
    setEditLabel(topic.label);
    setEditQuery(topic.query);
    setEditCadence(topic.cadence);
    setEditing(true);
  }

  async function saveEdit() {
    await patch({ label: editLabel, query: editQuery, cadence: editCadence });
    setEditing(false);
  }

  async function onDelete() {
    if (!topic || topic.source !== "user") return;
    if (!globalThis.confirm(`Delete topic “${topic.label}”?`)) return;
    await remove();
    navigate(paths.topics);
  }

  if (loading && !topic) {
    return (
      <PageFrame>
        <p>Loading topic…</p>
      </PageFrame>
    );
  }

  if (!topic) {
    return (
      <PageFrame>
        <p className="ui-error">{error ?? "Topic not found."}</p>
        <Link to={paths.topics}>Back to topics</Link>
      </PageFrame>
    );
  }

  return (
    <PageFrame>
      <PageHeader
        title={topic.label}
        description={topic.query}
        meta={
          <AppBreadcrumbs
            items={[
              { label: "Topics", to: paths.topics },
              { label: topic.label },
            ]}
          />
        }
        actions={
          <>
            <button type="button" className="ui-btn ui-btn--ghost" onClick={() => void togglePin()}>
              {topic.pinned ? "Unpin" : "Pin"}
            </button>
            <button type="button" className="ui-btn ui-btn--ghost" onClick={() => void refresh()} disabled={refreshing}>
              {refreshing ? "Refreshing…" : "Refresh"}
            </button>
            <Link to={batchUrl} className="ui-btn ui-btn--primary">
              Batch analyze
            </Link>
          </>
        }
      />

      {error ? <p className="ui-error">{error}</p> : null}

      <div className="topics-detail-grid">
        <div className="topics-detail-main">
          <Panel title="Theme summary">
            <ThemeSummary summary={latestRun?.theme_summary} />
          </Panel>
          <Panel title="Ticker candidates">
            <p className="ui-hint topics-watchlist-hint">
              <strong>+ Watchlist</strong> saves to your browser list on{" "}
              <Link to={paths.watchlists}>Watchlists</Link>. For overnight auto-scan jobs, add symbols on{" "}
              <Link to={paths.monitor}>Monitor</Link>.
            </p>
            {candidates.length === 0 ? (
              <p className="topics-empty">No candidates extracted yet.</p>
            ) : (
              <div className="topics-candidates-list">
                {candidates.map((c) => (
                  <TickerCandidateRow key={c.ticker} candidate={c} onAddWatchlist={addToWatchlist} />
                ))}
              </div>
            )}
          </Panel>
        </div>
        <aside className="topics-detail-side">
          <Panel title="Settings">
            {editing ? (
              <div className="topics-edit-form">
                <label>
                  Label
                  <input className="ui-input" value={editLabel} onChange={(e) => setEditLabel(e.target.value)} />
                </label>
                <label>
                  Query
                  <input className="ui-input" value={editQuery} onChange={(e) => setEditQuery(e.target.value)} />
                </label>
                <label>
                  Cadence
                  <CadenceSelect value={editCadence} onChange={setEditCadence} />
                </label>
                <div className="ui-form-row">
                  <button type="button" className="ui-btn ui-btn--primary" onClick={() => void saveEdit()}>
                    Save
                  </button>
                  <button type="button" className="ui-btn ui-btn--ghost" onClick={() => setEditing(false)}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="topics-meta">
                <p>
                  <strong>Cadence:</strong> {topic.cadence}
                </p>
                <p>
                  <strong>Source:</strong> {topic.source}
                </p>
                {topic.last_run_at ? (
                  <p>
                    <strong>Last run:</strong> {new Date(topic.last_run_at).toLocaleString()}
                  </p>
                ) : null}
                <button type="button" className="ui-btn ui-btn--ghost" onClick={startEdit}>
                  Edit
                </button>
                {topic.source === "user" ? (
                  <button type="button" className="ui-btn ui-btn--ghost ui-btn--danger" onClick={() => void onDelete()}>
                    Delete
                  </button>
                ) : null}
              </div>
            )}
          </Panel>
          <Panel title="Source articles">
            <ArticleList articles={articles} />
          </Panel>
          {runs.length > 1 ? (
            <Panel title="Run history">
              <ul className="topics-run-history">
                {runs.map((r) => (
                  <li key={r.run_id}>
                    {new Date(r.started_at).toLocaleString()} · {r.status} ({r.candidates.length} tickers)
                  </li>
                ))}
              </ul>
            </Panel>
          ) : null}
        </aside>
      </div>

      <p className="page-lead">
        <Link to={paths.topics}>← All topics</Link>
      </p>
    </PageFrame>
  );
}
