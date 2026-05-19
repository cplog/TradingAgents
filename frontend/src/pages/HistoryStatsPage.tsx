import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchHistoryRuns, type HistoryRunRef } from "../api";

function normalizeRating(r: string | null | undefined): string {
  if (!r || typeof r !== "string") return "Unknown";
  return r.trim();
}

export function HistoryStatsPage() {
  const [runs, setRuns] = useState<HistoryRunRef[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
    <div style={{ maxWidth: 840 }}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "var(--spacing-16)",
          flexWrap: "wrap",
          marginBottom: "var(--spacing-24)",
        }}
      >
        <h1 style={{ fontSize: "var(--text-heading-md)", fontWeight: 600 }}>
          History statistics
        </h1>
        <Link
          to="/history"
          style={{
            color: "var(--color-chartwell-blue)",
            fontWeight: 600,
            textDecoration: "none",
          }}
        >
          ← Back to History
        </Link>
      </div>

      <p style={{ color: "var(--color-ash-gray)", marginBottom: "var(--spacing-24)" }}>
        Aggregates from the latest{" "}
        <span className="mono">GET /api/history/runs?limit=500</span> snapshot (ratings and
        confidence only — not realized returns).
      </p>

      {loading ? <p>Loading…</p> : null}
      {error ? (
        <p style={{ color: "#b91c1c" }} role="alert">
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
            <div
              style={{
                padding: "var(--spacing-16)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-stone-border)",
                background: "var(--surface-cloud-white)",
              }}
            >
              <div style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>
                Runs in sample
              </div>
              <div style={{ fontSize: "28px", fontWeight: 700 }}>{stats.total}</div>
            </div>
            <div
              style={{
                padding: "var(--spacing-16)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-stone-border)",
                background: "var(--surface-cloud-white)",
              }}
            >
              <div style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>
                Avg confidence
              </div>
              <div style={{ fontSize: "28px", fontWeight: 700 }}>
                {stats.avgConf != null ? `${Math.round(stats.avgConf * 100)}%` : "—"}
              </div>
            </div>
          </div>

          <h2 style={{ fontSize: "var(--text-title)", fontWeight: 600, marginBottom: 12 }}>
            Rating distribution
          </h2>
          {ratingRows.length === 0 ? (
            <p style={{ color: "var(--color-ash-gray)" }}>No runs with ratings yet.</p>
          ) : (
            <table className="markdown-table-wrap" style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid var(--color-stone-border)" }}>
                  <th style={{ padding: "8px 12px" }}>Rating</th>
                  <th style={{ padding: "8px 12px" }}>Count</th>
                  <th style={{ padding: "8px 12px" }}>Share</th>
                </tr>
              </thead>
              <tbody>
                {ratingRows.map(([label, count]) => (
                  <tr key={label} style={{ borderBottom: "1px solid var(--color-stone-border)" }}>
                    <td style={{ padding: "8px 12px", fontWeight: 600 }}>{label}</td>
                    <td style={{ padding: "8px 12px" }}>{count}</td>
                    <td style={{ padding: "8px 12px" }}>
                      {stats.total ? `${Math.round((count / stats.total) * 100)}%` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      ) : null}
    </div>
  );
}
