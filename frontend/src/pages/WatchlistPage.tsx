import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

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

  return (
    <div style={{ maxWidth: 720 }}>
      <h1 style={{ fontSize: "var(--text-heading-md)", fontWeight: 600 }}>
        Watchlists
      </h1>
      <p style={{ color: "var(--color-ash-gray)", marginBottom: "var(--spacing-24)" }}>
        Stored locally in this browser ({STORAGE_KEY}). Use links to open the Analysis
        page with a ticker pre-filled.
      </p>

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
            border: "none",
            background: "var(--color-chartwell-blue)",
            color: "#fff",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Add
        </button>
      </div>
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
                  to={`/dashboard?ticker=${encodeURIComponent(t)}`}
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
    </div>
  );
}
