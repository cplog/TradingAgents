import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { dashboardPath, paths } from "../navigation/routes";
import { PageFrame, PageHeader } from "../components/PageFrame";
import { CadenceSelect } from "../components/topics/CadenceSelect";
import { searchTopic, type TopicCadence } from "../api";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

const STORAGE_KEY = "ta:watchlist";

function loadTickers(): string[] {
  try {
    const raw = globalThis.localStorage?.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((x): x is string => typeof x === "string")
      .map((t) => t.trim())
      .filter(Boolean);
  } catch {
    return [];
  }
}

function saveTickers(tickers: string[]) {
  globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(tickers));
}

export function WatchlistPage() {
  const [tickers, setTickers] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pinOpen, setPinOpen] = useState(false);
  const [pinLabel, setPinLabel] = useState("");
  const [pinQuery, setPinQuery] = useState("");
  const [pinCadence, setPinCadence] = useState<TopicCadence>("weekly");
  const [pinBusy, setPinBusy] = useState(false);
  useDocumentTitle("Watchlists");

  useEffect(() => {
    setTickers(loadTickers());
  }, []);

  const persist = useCallback((next: string[]) => {
    setTickers(next);
    saveTickers(next);
  }, []);

  function addTicker() {
    setError(null);
    const t = input.trim().toUpperCase();
    if (!t) {
      setError("Enter a symbol.");
      return;
    }
    if (tickers.includes(t)) {
      setError("Already on the list.");
      return;
    }
    persist([...tickers, t]);
    setInput("");
  }

  function removeTicker(t: string) {
    persist(tickers.filter((x) => x !== t));
  }

  function openPinModal() {
    setPinLabel(tickers.length ? `${tickers.slice(0, 3).join(", ")} watchlist` : "My watchlist");
    setPinQuery(tickers.join(" "));
    setPinOpen(true);
  }

  async function submitPinTopic() {
    setPinBusy(true);
    setError(null);
    try {
      const q = pinQuery.trim() || tickers.join(" ");
      if (!q) {
        setError("Add tickers or enter a theme query.");
        return;
      }
      await searchTopic({ query: q, label: pinLabel.trim() || undefined, cadence: pinCadence });
      setPinOpen(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPinBusy(false);
    }
  }

  return (
    <PageFrame>
      <PageHeader
        title="Watchlists"
        description="Browser-local symbol shortcuts for manual Analysis. Stored only in this browser (localStorage key ta:watchlist)."
        meta={<AppBreadcrumbs items={[{ label: "Watchlists" }]} />}
      />

      <aside className="reading-callout" aria-label="Watchlist vs monitor">
        For <strong>automated overnight scanning</strong> of large US drops (barbell signal → scan jobs), add tickers
        to the server watchlist on the <Link to={paths.monitor}>Monitor</Link> page instead. That list is saved on the
        API host and is separate from this page.
      </aside>

      <div
        style={{
          display: "flex",
          gap: "var(--spacing-8)",
          flexWrap: "wrap",
          marginBottom: "var(--spacing-16)",
        }}
      >
        <input
          type="text"
          value={input}
          placeholder="e.g. AAPL"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") addTicker();
          }}
          style={{
            flex: "1 1 200px",
            padding: "var(--spacing-8) var(--spacing-12)",
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--color-stone-border)",
            fontFamily: "var(--font-roobert), var(--font-inter)",
          }}
        />
        <button
          type="button"
          onClick={addTicker}
          style={{
            padding: "var(--spacing-8) var(--spacing-16)",
            borderRadius: "var(--radius-md)",
            background: "var(--color-phosphor-glow)",
            color: "var(--color-phosphor)",
            border: "1px solid var(--color-phosphor-dim)",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Add
        </button>
        <button
          type="button"
          onClick={openPinModal}
          style={{
            padding: "var(--spacing-8) var(--spacing-16)",
            borderRadius: "var(--radius-md)",
            background: "transparent",
            color: "var(--color-chartwell-blue)",
            border: "1px solid var(--color-stone-border)",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Pin as topic
        </button>
      </div>
      {pinOpen ? (
        <div className="topics-pin-modal" role="dialog" aria-label="Pin as topic">
          <h3>Pin watchlist as topic</h3>
          <label>
            Label
            <input className="ui-input" value={pinLabel} onChange={(e) => setPinLabel(e.target.value)} />
          </label>
          <label>
            Search query
            <input className="ui-input" value={pinQuery} onChange={(e) => setPinQuery(e.target.value)} />
          </label>
          <label>
            Cadence
            <CadenceSelect value={pinCadence} onChange={setPinCadence} />
          </label>
          <div style={{ display: "flex", gap: "var(--spacing-8)", marginTop: "var(--spacing-12)" }}>
            <button type="button" className="ui-btn ui-btn--primary" disabled={pinBusy} onClick={() => void submitPinTopic()}>
              {pinBusy ? "Creating…" : "Create topic"}
            </button>
            <button type="button" className="ui-btn ui-btn--ghost" onClick={() => setPinOpen(false)}>
              Cancel
            </button>
            <Link to={paths.topics} className="ui-btn ui-btn--ghost">
              Open topics
            </Link>
          </div>
        </div>
      ) : null}
      {error ? (
        <p style={{ color: "#b91c1c", marginBottom: "var(--spacing-12)" }}>{error}</p>
      ) : null}

      {tickers.length === 0 ? (
        <p style={{ color: "var(--color-ash-gray)" }}>No symbols yet.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {tickers.map((t) => (
            <li
              key={t}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "var(--spacing-12)",
                borderBottom: "1px solid var(--color-stone-border)",
                gap: "var(--spacing-12)",
              }}
            >
              <span className="mono" style={{ fontWeight: 600 }}>
                {t}
              </span>
              <span style={{ display: "flex", gap: "var(--spacing-8)" }}>
                <Link
                  to={dashboardPath({ ticker: t })}
                  style={{
                    color: "var(--color-chartwell-blue)",
                    fontWeight: 600,
                    textDecoration: "none",
                  }}
                >
                  Analyze
                </Link>
                <button
                  type="button"
                  onClick={() => removeTicker(t)}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--color-ash-gray)",
                    cursor: "pointer",
                    textDecoration: "underline",
                  }}
                >
                  Remove
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </PageFrame>
  );
}
