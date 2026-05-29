import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";
import { paths, runsPath } from "../navigation/routes";
import { PageFrame, PageHeader } from "../components/PageFrame";
import { HistoryRatingChart } from "../components/charts/HistoryRatingChart";
import {
  fetchHistoryRun,
  fetchHistoryRuns,
  postHistoryCompare,
  submitAnalyze,
  type HistoryCompareResponse,
  type HistoryRunRef,
} from "../api";
import { buildRerunAnalyzePayload } from "../utils/historyRerun";
import {
  formatHistoryTimestampWithZone,
  mergeHistoryAndJobs,
  sortHistoryRows,
  type HistoryTableRow,
} from "../utils/historyDisplay";
import { fetchJobs } from "../api";
import { formatLlmLabel, formatSourcesLabel, provenanceTitle } from "../utils/runProvenance";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

function pct(conf: number | null | undefined): string {
  if (conf == null || !Number.isFinite(conf)) return "—";
  return `${Math.round(conf * 100)}%`;
}

export function StockPage() {
  const { ticker: rawTicker } = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(rawTicker ?? "").trim().toUpperCase();
  const navigate = useNavigate();
  const [runs, setRuns] = useState<HistoryTableRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runIdA, setRunIdA] = useState("");
  const [runIdB, setRunIdB] = useState("");
  const [compare, setCompare] = useState<HistoryCompareResponse | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  useDocumentTitle(ticker ? `${ticker} — Stock history` : "Stock");

  const load = useCallback(async () => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    try {
      const [history, jobs] = await Promise.all([
        fetchHistoryRuns({ ticker, limit: 100 }),
        fetchJobs(50),
      ]);
      const merged = mergeHistoryAndJobs(history, jobs, { ticker });
      const completed = merged.filter((r) => r.job_status === "completed");
      setRuns(sortHistoryRows(completed, "processing_desc"));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setRuns([]);
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => {
    void load();
  }, [load]);

  const latest = runs[0] ?? null;
  const historyRefs: HistoryRunRef[] = useMemo(
    () =>
      runs.map((r) => ({
        run_id: r.run_id,
        ticker: r.ticker,
        date: r.date,
        rating: r.rating,
        confidence: r.confidence,
        completed_at: r.completed_at,
        created_at: r.created_at,
      })),
    [runs],
  );

  async function onCompare() {
    if (!runIdA.trim() || !runIdB.trim()) return;
    setCompareLoading(true);
    setCompareError(null);
    try {
      const res = await postHistoryCompare(runIdA.trim(), runIdB.trim());
      setCompare(res);
    } catch (e: unknown) {
      setCompareError(e instanceof Error ? e.message : String(e));
      setCompare(null);
    } finally {
      setCompareLoading(false);
    }
  }

  async function onRerunLatest() {
    if (!latest) return;
    try {
      const detail = await fetchHistoryRun(latest.run_id);
      const body = buildRerunAnalyzePayload(detail);
      const r = await submitAnalyze(body);
      navigate(runsPath(r.job_id));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (!ticker) {
    return (
      <PageFrame>
        <p>Missing ticker.</p>
      </PageFrame>
    );
  }

  return (
    <PageFrame className="stock-page">
      <PageHeader
        title={ticker}
        description="Stock-level view — all persisted runs for this symbol. Open a run for the full report; compare runs with matching model and data setup."
        meta={
          <>
            <AppBreadcrumbs
              items={[
                { label: "Runs", to: paths.history },
                { label: ticker },
              ]}
            />
          </>
        }
      />

      {error && <p className="notice notice--error">{error}</p>}
      {loading && <p className="ui-muted">Loading runs…</p>}

      {latest && (
        <section className="stock-page__summary">
          <div>
            <p className="ui-label">Latest completed</p>
            <p className="stock-page__latest-rating">{latest.rating ?? "—"}</p>
            <p className="ui-muted">
              {latest.date} · {pct(latest.confidence)} ·{" "}
              {formatHistoryTimestampWithZone(latest.completed_at ?? latest.created_at)}
            </p>
          </div>
          <div className="stock-page__summary-actions">
            <Link to={runsPath(latest.run_id)} className="ui-btn-primary" style={{ textDecoration: "none" }}>
              Open latest run
            </Link>
            <button type="button" className="ui-btn-secondary" onClick={() => void onRerunLatest()}>
              Rerun latest setup
            </button>
          </div>
        </section>
      )}

      {historyRefs.length >= 2 && (
        <section className="stock-page__chart">
          <h2 className="ui-label">Rating over time</h2>
          <HistoryRatingChart runs={historyRefs} />
        </section>
      )}

      <section className="stock-page__runs">
        <h2>Runs for {ticker} ({runs.length})</h2>
        {runs.length === 0 && !loading ? (
          <p className="ui-muted">No completed runs for this ticker yet.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="history-runs-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Date</th>
                  <th>Rating</th>
                  <th>Confidence</th>
                  <th>Model</th>
                  <th>Sources</th>
                  <th>Completed (HKT)</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.run_id}>
                    <td className="mono">{r.run_id}</td>
                    <td>{r.date}</td>
                    <td>{r.rating}</td>
                    <td>{pct(r.confidence)}</td>
                    <td title={provenanceTitle(r.provenance)}>{formatLlmLabel(r.provenance)}</td>
                    <td title={provenanceTitle(r.provenance)}>{formatSourcesLabel(r.provenance)}</td>
                    <td>{formatHistoryTimestampWithZone(r.completed_at ?? r.created_at)}</td>
                    <td>
                      <Link to={runsPath(r.run_id)} className="link-action">
                        Open run →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {runs.length >= 2 && (
        <section className="stock-page__compare">
          <h2>Compare two runs</h2>
          <p className="reading-callout">
            Pick two runs for {ticker} with the same <strong>Model</strong> and <strong>Sources</strong> when possible.
          </p>
          <div className="stock-page__compare-pickers">
            <label>
              Run A
              <select value={runIdA} onChange={(e) => setRunIdA(e.target.value)}>
                <option value="">Select…</option>
                {runs.map((r) => (
                  <option key={`a-${r.run_id}`} value={r.run_id}>
                    {r.run_id} · {r.date} · {r.rating}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Run B
              <select value={runIdB} onChange={(e) => setRunIdB(e.target.value)}>
                <option value="">Select…</option>
                {runs.map((r) => (
                  <option key={`b-${r.run_id}`} value={r.run_id}>
                    {r.run_id} · {r.date} · {r.rating}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="ui-btn-primary" disabled={compareLoading} onClick={() => void onCompare()}>
              {compareLoading ? "Comparing…" : "Compare"}
            </button>
          </div>
          {compareError && <p className="notice notice--error">{compareError}</p>}
          {compare && (
            <div className="stock-page__compare-result">
              <p>
                <strong>A:</strong> {compare.a.rating} ({compare.a.date}) · <strong>B:</strong>{" "}
                {compare.b.rating} ({compare.b.date})
              </p>
            </div>
          )}
        </section>
      )}
    </PageFrame>
  );
}
