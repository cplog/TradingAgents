import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  addMonitorWatchlistTicker,
  fetchMonitorSignals,
  fetchMonitorStatus,
  fetchMonitorWatchlist,
  removeMonitorWatchlistTicker,
  triggerMonitorTick,
  type MonitorSignal,
  type MonitorStatus,
} from "../api";
import { PageFrame, PageHeader, Panel } from "../components/PageFrame";
import { paths, runsPath } from "../navigation/routes";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

const EXAMPLE_TICKERS = ["NVDA", "AAPL", "TSLA", "AMD"] as const;

function sessionLabel(session: string): string {
  switch (session) {
    case "premarket":
      return "US pre-market (4:00–9:30 ET)";
    case "overnight":
      return "US overnight / after-hours (20:00–4:00 ET)";
    case "regular":
      return "US regular session (9:30–16:00 ET)";
    case "closed":
      return "US closed (16:00–20:00 ET)";
    default:
      return session;
  }
}

export function MonitorPage() {
  const [status, setStatus] = useState<MonitorStatus | null>(null);
  const [tickers, setTickers] = useState<string[]>([]);
  const [signals, setSignals] = useState<MonitorSignal[]>([]);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useDocumentTitle("Monitor");

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [st, wl, sig] = await Promise.all([
        fetchMonitorStatus(),
        fetchMonitorWatchlist(),
        fetchMonitorSignals(30),
      ]);
      setStatus(st);
      setTickers(wl.tickers);
      setSignals(sig.signals);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function addTicker(symRaw?: string) {
    const sym = (symRaw ?? input).trim().toUpperCase();
    if (!sym) return;
    setBusy(true);
    setError(null);
    try {
      const res = await addMonitorWatchlistTicker(sym);
      setTickers(res.tickers);
      setInput("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function removeTicker(sym: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await removeMonitorWatchlistTicker(sym);
      setTickers(res.tickers);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runTick() {
    setBusy(true);
    setError(null);
    try {
      await triggerMonitorTick();
      await refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const monitorDisabled = status && !status.enabled;
  const watchlistEmpty = tickers.length === 0;
  const pollingIdle = status?.enabled && !status.should_poll;

  return (
    <PageFrame className="monitor-page">
      <PageHeader
        title="Overnight monitor"
        description="Automated barbell-dip scanner for US names on your server watchlist. When a symbol drops hard during extended hours and scores high enough, the server queues a lightweight scan analysis."
        meta={<AppBreadcrumbs items={[{ label: "Monitor" }]} />}
      />

      <aside className="reading-callout monitor-page__howto" aria-label="How overnight monitor works">
        <strong>How it works</strong>
        <ol className="monitor-page__steps">
          <li>Add US tickers to the <strong>server watchlist</strong> below (saved on the API host, not in your browser).</li>
          <li>During US pre-market or overnight ET, the server polls AKShare for large daily drops (default ≤ −10%).</li>
          <li>
            Tickers on your list that appear in that scan get an overnight signal score (barbell trend cloud + bias).
            Score ≥ {status?.threshold ?? 75} triggers a scan-mode job automatically.
          </li>
          <li>
            Triggered jobs appear under <strong>Recent signals</strong> and in{" "}
            <Link to={paths.history}>History</Link> (filter: overnight / scan).
          </li>
        </ol>
        <p className="monitor-page__compare">
          Not the same as{" "}
          <Link to={paths.watchlists}>Watchlists</Link> — that page is a browser-local shortcut list for manual
          Analysis. Only symbols on this page participate in automated overnight scanning.
        </p>
      </aside>

      {error ? (
        <p className="ui-error" role="alert">
          {error}
          {(error.includes("404") || error.includes("405")) && (
            <>
              {" "}
              Restart the FastAPI server on port 8808 — an older uvicorn process may be running without{" "}
              <code>/api/monitor</code> routes.
            </>
          )}
        </p>
      ) : null}

      {monitorDisabled ? (
        <div className="monitor-page__banner monitor-page__banner--warn" role="status">
          <strong>Background monitor is off.</strong> Automatic polling will not run until you set{" "}
          <code className="mono">TRADINGAGENTS_MONITOR_ENABLED=true</code> in <code>.env</code> and restart the API.
          You can still add tickers and use <strong>Run poll now</strong> for a manual check.
        </div>
      ) : null}

      {pollingIdle && status ? (
        <div className="monitor-page__banner monitor-page__banner--info" role="status">
          <strong>Automatic polling is idle.</strong> Current US session: {sessionLabel(status.session)}. Background
          polls run only during pre-market and overnight ET. Use <strong>Run poll now</strong> to test anytime.
        </div>
      ) : null}

      <Panel title="Session">
        {status ? (
          <>
            <ul className="monitor-page__meta">
              <li>
                <strong>Enabled:</strong> {status.enabled ? "yes" : "no"}
              </li>
              <li>
                <strong>US session:</strong> {sessionLabel(status.session)}
              </li>
              <li>
                <strong>Polling:</strong> {status.should_poll ? "active" : "idle"} ({status.poll_seconds}s interval,
                score threshold {status.threshold})
              </li>
              <li>
                <strong>Last tick:</strong> {status.last_tick ?? "—"}
              </li>
              {status.last_candidates.length > 0 ? (
                <li>
                  <strong>Last scan hits on your list:</strong> {status.last_candidates.join(", ")}
                </li>
              ) : null}
              {status.last_errors.length > 0 ? (
                <li className="monitor-page__meta-errors">
                  <strong>Last errors:</strong> {status.last_errors.join("; ")}
                </li>
              ) : null}
            </ul>
            <button
              type="button"
              className="ui-btn-secondary"
              disabled={busy}
              onClick={() => void runTick()}
            >
              Run poll now
            </button>
          </>
        ) : (
          <p>Loading…</p>
        )}
      </Panel>

      <Panel title="Server watchlist (API)">
        {watchlistEmpty ? (
          <div className="monitor-page__empty-watchlist" role="status">
            <p className="monitor-page__empty-title">Add at least one ticker to get started</p>
            <p className="ui-muted">
              The monitor only scores symbols you list here. Start with names you would watch for overnight panic
              dips, then wait for extended hours or click Run poll now.
            </p>
          </div>
        ) : (
          <p className="ui-hint">
            {tickers.length} ticker{tickers.length === 1 ? "" : "s"} on the server list. These are intersected with
            the AKShare US drop scan before scoring.
          </p>
        )}

        <div className="monitor-page__add-row">
          <input
            type="text"
            value={input}
            placeholder="e.g. NVDA"
            aria-label="Add ticker to server watchlist"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void addTicker();
            }}
          />
          <button type="button" className="ui-btn-primary" disabled={busy} onClick={() => void addTicker()}>
            Add
          </button>
        </div>

        {watchlistEmpty ? (
          <div className="monitor-page__examples">
            <span className="monitor-page__examples-label">Quick add:</span>
            {EXAMPLE_TICKERS.map((sym) => (
              <button
                key={sym}
                type="button"
                className="ui-btn-ghost monitor-page__example-chip"
                disabled={busy}
                onClick={() => void addTicker(sym)}
              >
                {sym}
              </button>
            ))}
          </div>
        ) : null}

        {!watchlistEmpty ? (
          <ul className="monitor-page__watchlist">
            {tickers.map((t) => (
              <li key={t}>
                <span className="mono">{t}</span>
                <button type="button" className="ui-btn-ghost" disabled={busy} onClick={() => void removeTicker(t)}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </Panel>

      <Panel title="Recent signals">
        {signals.length === 0 ? (
          <div className="monitor-page__empty-signals" role="status">
            <p className="ui-muted">No triggered signals yet.</p>
            <ul className="monitor-page__empty-reasons">
              {watchlistEmpty ? <li>Server watchlist is empty — add tickers first.</li> : null}
              {monitorDisabled ? <li>Background monitor is disabled — enable it or use Run poll now.</li> : null}
              {!watchlistEmpty && !monitorDisabled ? (
                <>
                  <li>No watchlist symbol had a large enough drop and score ≥ {status?.threshold ?? 75} yet.</li>
                  <li>Polling may be idle outside US pre-market / overnight hours.</li>
                </>
              ) : null}
            </ul>
            <p className="monitor-page__empty-actions">
              <button type="button" className="ui-btn-secondary" disabled={busy} onClick={() => void runTick()}>
                Run poll now
              </button>{" "}
              · <Link to={paths.history}>View history</Link>
            </p>
          </div>
        ) : (
          <table className="ui-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Score</th>
                <th>Change</th>
                <th>Job</th>
                <th>At</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s, i) => (
                <tr key={`${s.ticker}-${s.at ?? i}`}>
                  <td className="mono">{s.ticker}</td>
                  <td>{s.score}</td>
                  <td>{s.change_pct != null ? `${s.change_pct.toFixed(2)}%` : "—"}</td>
                  <td>
                    {s.job_id ? <Link to={runsPath(s.job_id)}>{s.job_id}</Link> : "—"}
                  </td>
                  <td>{s.at ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </PageFrame>
  );
}
