import { useState } from "react";
import { Link } from "react-router-dom";
import { getDimensionsByTicker } from "../api";
import { FactorBar } from "../components/dimensions/FactorBar";
import { Pressable } from "../components/Pressable";
import type { FactorScores, StockDimensions } from "../dimensions-types";

interface Row {
  ticker: string;
  dimensions: StockDimensions | null;
  error?: string;
}

const FACTOR_KEYS: (keyof FactorScores)[] = [
  "value",
  "growth",
  "quality",
  "momentum",
  "low_risk",
  "sentiment",
];

const FACTOR_HEADERS = ["Value", "Growth", "Quality", "Momentum", "Low Risk", "Sentiment"];

export function ScreenerPage() {
  const [input, setInput] = useState("AAPL, MSFT, NVDA");
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setError(null);
    setLoading(true);
    const tickers = Array.from(
      new Set(
        input
          .split(/[,\n]/)
          .map((s) => s.trim().toUpperCase())
          .filter(Boolean)
      )
    );
    if (!tickers.length) {
      setLoading(false);
      setError("Enter at least one ticker.");
      return;
    }
    try {
      const results: Row[] = await Promise.all(
        tickers.map(async (t) => {
          try {
            const d = await getDimensionsByTicker(t);
            return { ticker: t, dimensions: d };
          } catch (e: unknown) {
            return {
              ticker: t,
              dimensions: null,
              error: e instanceof Error ? e.message : String(e),
            };
          }
        })
      );
      setRows(results);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: "1200px" }}>
      <header style={{ marginBottom: "var(--spacing-16)" }}>
        <h1 style={{ margin: 0, fontSize: "var(--text-heading-lg)" }}>Screener</h1>
        <p style={{ margin: "8px 0 0", color: "var(--color-ash-gray)" }}>
          Facts-only dimensions preview. Enter tickers below to fetch a fast,
          deterministic factor snapshot. Trigger a full agent run from any row.
        </p>
      </header>

      <section
        style={{
          background: "var(--surface-cloud-white)",
          padding: "var(--card-padding)",
          borderRadius: "var(--radius-cards)",
          border: "1px solid var(--color-stone-border)",
          boxShadow: "var(--shadow-subtle)",
          marginBottom: "var(--spacing-16)",
        }}
      >
        <label style={{ display: "block", marginBottom: 8, fontSize: "var(--text-caption)" }}>
          Tickers (comma or newline separated)
        </label>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={3}
          style={{
            width: "100%",
            padding: "var(--spacing-12)",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--color-platinum-outline)",
            fontFamily: "inherit",
          }}
        />
        <div style={{ marginTop: 12, display: "flex", gap: 12, alignItems: "center" }}>
          <Pressable
            onClick={() => void run()}
            disabled={loading}
            style={{
              padding: "10px 20px",
              borderRadius: "var(--radius-buttons)",
              background: loading
                ? "var(--color-platinum-outline)"
                : "var(--color-chartwell-blue)",
              color: "white",
              border: "none",
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "Loading…" : "Fetch dimensions"}
          </Pressable>
          {error && <span style={{ color: "#b91c1c", fontSize: 13 }}>{error}</span>}
        </div>
      </section>

      {rows.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              background: "var(--surface-cloud-white)",
              borderRadius: "var(--radius-md)",
              overflow: "hidden",
              boxShadow: "var(--shadow-subtle)",
              fontSize: 13,
            }}
          >
            <thead>
              <tr style={{ background: "var(--color-sky-tint)", textAlign: "left" }}>
                <th style={{ padding: 12 }}>Ticker</th>
                {FACTOR_HEADERS.map((h) => (
                  <th key={h} style={{ padding: 12, whiteSpace: "nowrap" }}>
                    {h}
                  </th>
                ))}
                <th style={{ padding: 12 }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.ticker}
                  style={{ borderTop: "1px solid var(--color-stone-border)" }}
                >
                  <td style={{ padding: 12 }} className="mono">
                    <strong>{row.ticker}</strong>
                    {row.dimensions?.source === "facts_only" && (
                      <span
                        style={{
                          marginLeft: 6,
                          fontSize: 10,
                          color: "var(--color-ash-gray)",
                          fontWeight: 400,
                        }}
                      >
                        facts only
                      </span>
                    )}
                    {row.error && (
                      <div style={{ fontSize: 11, color: "#b91c1c", marginTop: 4 }}>
                        {row.error}
                      </div>
                    )}
                  </td>
                  {FACTOR_KEYS.map((k) => (
                    <td key={k} style={{ padding: "4px 8px" }}>
                      <FactorBar
                        label=""
                        score={row.dimensions?.factor_scores[k]?.score ?? null}
                        width={80}
                      />
                    </td>
                  ))}
                  <td style={{ padding: 12 }}>
                    <Link
                      to={`/dashboard?ticker=${encodeURIComponent(row.ticker)}`}
                      style={{
                        color: "var(--color-chartwell-blue)",
                        fontWeight: 600,
                        textDecoration: "none",
                      }}
                    >
                      Run full analysis →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default ScreenerPage;
