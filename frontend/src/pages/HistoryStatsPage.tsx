import { useEffect, useMemo, useState } from "react";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";
import { paths } from "../navigation/routes";
import { PageFrame, PageHeader } from "../components/PageFrame";
import { HistoryRatingChart } from "../components/charts/HistoryRatingChart";
import { fetchHistoryRuns, type HistoryRunRef } from "../api";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

function normalizeRating(r: string | null | undefined): string {
  if (!r || typeof r !== "string") return "Unknown";
  return r.trim();
}

export function HistoryStatsPage() {
  const [runs, setRuns] = useState<HistoryRunRef[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useDocumentTitle("Run stats");

  useEffect(() => {
    let cancelled = false;
    void fetchHistoryRuns({ limit: 500 })
      .then((rows) => {
        if (!cancelled) {
          setRuns(rows);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const stats = useMemo(() => {
    const byRating: Record<string, number> = {};
    let confSum = 0;
    let confN = 0;
    for (const row of runs) {
      const label = normalizeRating(row.rating);
      byRating[label] = (byRating[label] ?? 0) + 1;
      if (typeof row.confidence === "number" && Number.isFinite(row.confidence)) {
        confSum += row.confidence;
        confN += 1;
      }
    }
    const avgConf = confN > 0 ? confSum / confN : null;
    return { byRating, avgConf, total: runs.length };
  }, [runs]);

  const ratingRows = Object.entries(stats.byRating).sort((a, b) => b[1] - a[1]);

  return (
    <PageFrame>
      <PageHeader
        title="Run statistics"
        meta={
          <>
            <AppBreadcrumbs
              items={[
                { label: "Runs", to: paths.history },
                { label: "Statistics" },
              ]}
            />
          </>
        }
      />

      <p className="page-lead">
        Aggregates from the latest <span className="mono">GET /api/history/runs?limit=500</span> snapshot (ratings and
        confidence only, not realized returns).
      </p>

      {loading ? <p>Loading…</p> : null}
      {error ? (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      ) : null}

      {!loading && !error ? (
        <>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
              gap: "var(--spacing-16)",
              marginBottom: "var(--spacing-24)",
            }}
          >
            <div className="stat-card">
              <div className="stat-card__label">Runs in sample</div>
              <div className="stat-card__value">{stats.total}</div>
            </div>
            <div className="stat-card">
              <div className="stat-card__label">Avg confidence</div>
              <div className="stat-card__value">
                {stats.avgConf != null ? `${Math.round(stats.avgConf * 100)}%` : "—"}
              </div>
            </div>
          </div>

          <h2 style={{ fontSize: "var(--text-title)", fontWeight: 600 }} className="section-gap-sm">
            Rating distribution
          </h2>
          <HistoryRatingChart runs={runs} />

          {ratingRows.length === 0 ? (
            <p className="section-gap-sm" style={{ color: "var(--color-ash-gray)" }}>No runs with ratings yet.</p>
          ) : (
            <div className="ui-table-wrap" style={{ marginTop: 16 }}>
              <table className="ui-table">
                <thead>
                  <tr>
                    <th>Rating</th>
                    <th>Count</th>
                    <th>Share</th>
                  </tr>
                </thead>
                <tbody>
                  {ratingRows.map(([label, count]) => (
                    <tr key={label}>
                      <td style={{ fontWeight: 600 }}>{label}</td>
                      <td>{count}</td>
                      <td>{stats.total ? `${Math.round((count / stats.total) * 100)}%` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}
    </PageFrame>
  );
}
