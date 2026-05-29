import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { dashboardPath } from "../navigation/routes";
import { getDimensionsByTicker } from "../api";
import { FactorBar } from "../components/dimensions/FactorBar";
import { PageFrame, PageHeader } from "../components/PageFrame";
import { Pressable } from "../components/Pressable";
import type { FactorScores, StockDimensions } from "../dimensions-types";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

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
  const navigate = useNavigate();
  const [input, setInput] = useState("AAPL, MSFT, NVDA");
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  useDocumentTitle("Screener");

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
      setSelected(new Set(results.filter((r) => r.dimensions).map((r) => r.ticker)));
    } finally {
      setLoading(false);
    }
  }

  const selectedList = useMemo(() => [...selected].sort(), [selected]);

  function toggleTicker(t: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  }

  function sendToBatch() {
    if (!selectedList.length) return;
    const qs = new URLSearchParams({ tickers: selectedList.join(",") });
    navigate(`/batch?${qs.toString()}`);
  }

  return (
    <PageFrame wide>
      <PageHeader
        title="Screener"
        description="Facts-only dimensions preview — fast factor snapshot without full LLM cost."
      />

      <div className="flow-banner">
        <strong>Preview, not a full run.</strong> This page calls{" "}
        <span className="mono">GET /api/dimensions/{"{ticker}"}</span> for instant factor scores. For multi-agent
        reports and PM ratings, use Batch or Analysis from the sidebar.
      </div>

      <section className="ui-panel-section">
        <label className="ui-field">
          <span className="ui-field__label">Tickers (comma or newline separated)</span>
          <textarea className="ui-textarea" value={input} onChange={(e) => setInput(e.target.value)} rows={3} />
        </label>
        <div className="ui-form-row">
          <Pressable className="ui-btn-primary" onClick={() => void run()} disabled={loading}>
            {loading ? "Loading…" : "Fetch dimensions"}
          </Pressable>
          {error && <span className="notice notice--error">{error}</span>}
        </div>
      </section>

      {rows.length > 0 && (
        <div className="ui-form-row" style={{ marginBottom: "var(--spacing-12)" }}>
          <Pressable
            className="ui-btn-secondary"
            disabled={selectedList.length === 0}
            onClick={sendToBatch}
          >
            Send {selectedList.length || 0} to Batch →
          </Pressable>
          <button type="button" className="ui-btn-ghost" onClick={() => setSelected(new Set(rows.map((r) => r.ticker)))}>
            Select all
          </button>
          <button type="button" className="ui-btn-ghost" onClick={() => setSelected(new Set())}>
            Clear
          </button>
        </div>
      )}

      {rows.length > 0 && (
        <div className="ui-table-wrap">
          <table className="ui-table">
            <thead>
              <tr>
                <th style={{ width: 36 }}>
                  <span className="ui-label">Pick</span>
                </th>
                <th>Ticker</th>
                {FACTOR_HEADERS.map((h) => (
                  <th key={h} style={{ whiteSpace: "nowrap" }}>
                    {h}
                  </th>
                ))}
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.ticker}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selected.has(row.ticker)}
                      onChange={() => toggleTicker(row.ticker)}
                      aria-label={`Select ${row.ticker}`}
                    />
                  </td>
                  <td className="mono">
                    <strong>{row.ticker}</strong>
                    {row.dimensions?.source === "facts_only" && (
                      <span className="meta-tag meta-tag--muted" style={{ marginLeft: 6 }}>
                        facts only
                      </span>
                    )}
                    {row.error && <div className="notice notice--error" style={{ marginTop: 4, fontSize: 11 }}>{row.error}</div>}
                  </td>
                  {FACTOR_KEYS.map((k) => (
                    <td key={k} style={{ padding: "4px 8px" }}>
                      <FactorBar label="" score={row.dimensions?.factor_scores[k]?.score ?? null} width={80} />
                    </td>
                  ))}
                  <td>
                    <Link to={dashboardPath({ ticker: row.ticker })} className="link-action">
                      Run full analysis →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageFrame>
  );
}

export default ScreenerPage;
