import { useAutoAnimate } from "@formkit/auto-animate/react";
import { useMemo, useState } from "react";
import { Pressable } from "../components/Pressable";
import { fetchNews, type NewsItem, type NewsSource } from "../api";

function sentimentColor(s: NewsItem["sentiment"]) {
  if (s === "bullish") return { bg: "#dcfce7", fg: "#166534" };
  if (s === "bearish") return { bg: "#fee2e2", fg: "#991b1b" };
  return { bg: "#f5f5f4", fg: "#57534e" };
}

const SOURCE_LABEL: Record<NewsSource, string> = {
  yfinance: "Yahoo ticker",
  yfinance_macro: "Yahoo macro",
  finnhub: "Finnhub",
  google_rss: "Google RSS",
  akshare: "AKShare",
  reddit: "Reddit",
  stocktwits: "StockTwits",
  alpha_vantage: "Alpha Vantage",
};

const SOURCE_STYLE: Record<NewsSource, { bg: string; fg: string }> = {
  yfinance: { bg: "#e0f2fe", fg: "#0369a1" },
  yfinance_macro: { bg: "#fef3c7", fg: "#b45309" },
  finnhub: { bg: "#eef2ff", fg: "#3730a3" },
  google_rss: { bg: "#f0fdf4", fg: "#166534" },
  akshare: { bg: "#fdf2f8", fg: "#9d174d" },
  reddit: { bg: "#ffedd5", fg: "#c2410c" },
  stocktwits: { bg: "#ede9fe", fg: "#5b21b6" },
  alpha_vantage: { bg: "#ecfdf5", fg: "#047857" },
};

export function NewsPage() {
  const [listRef] = useAutoAnimate();
  const [ticker, setTicker] = useState("AAPL");
  const [items, setItems] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [sourceFilter, setSourceFilter] = useState<"all" | NewsSource>("all");
  const [sourceErrors, setSourceErrors] = useState<Record<string, string>>({});
  const [fetchedAt, setFetchedAt] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const r = await fetchNews(ticker.trim(), 50);
      setItems(r.items);
      setSourceErrors(r.source_errors ?? {});
      setFetchedAt(r.fetched_at ?? null);
    } finally {
      setLoading(false);
    }
  }

  const visible = useMemo(() => {
    if (sourceFilter === "all") return items;
    return items.filter((it) => (it.source ?? "yfinance") === sourceFilter);
  }, [items, sourceFilter]);

  const sourceCounts = useMemo(() => {
    const c: Record<NewsSource, number> = {
      yfinance: 0,
      yfinance_macro: 0,
      finnhub: 0,
      google_rss: 0,
      akshare: 0,
      reddit: 0,
      stocktwits: 0,
      alpha_vantage: 0,
    };
    for (const it of items) {
      const src = it.source ?? "yfinance";
      c[src] = (c[src] ?? 0) + 1;
    }
    return c;
  }, [items]);

  return (
    <div style={{ maxWidth: "720px" }}>
      <h1 style={{ marginTop: 0 }}>News and sentiment</h1>
      <p style={{ margin: "0 0 var(--spacing-12)", color: "var(--color-ash-gray)", fontSize: 15 }}>
        Raw streams merged: <strong>Yahoo ticker news</strong>, <strong>Yahoo macro search</strong> (same queries as the
        CLI global-news tool), <strong>Finnhub</strong>, <strong>Google RSS</strong>, <strong>AKShare</strong>,{" "}
        <strong>Alpha Vantage</strong> NEWS_SENTIMENT when{" "}
        <span className="mono">ALPHA_VANTAGE_API_KEY</span> is set, plus <strong>Reddit</strong> (WSB / stocks / investing
        search) and <strong>StockTwits</strong>. Sentiment uses keywords for text, AV labels when present, and StockTwits
        bull/bear tags — not an LLM.
      </p>
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          placeholder="Ticker"
          style={{ padding: 8, flex: 1, minWidth: 120, borderRadius: "var(--radius-inputs)" }}
        />
        <Pressable
          disabled={loading}
          onClick={() => void load().catch((e) => alert(String(e)))}
          style={{
            padding: "8px 16px",
            borderRadius: "var(--radius-buttons)",
            background: "var(--color-chartwell-blue)",
            color: "white",
            border: "none",
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          Load
        </Pressable>
      </div>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
          marginBottom: "var(--spacing-16)",
          alignItems: "center",
        }}
      >
        <span style={{ fontSize: "var(--text-caption)", color: "var(--color-steel-gray)" }}>Source:</span>
        {(
          [
            "all",
            "yfinance",
            "yfinance_macro",
            "finnhub",
            "google_rss",
            "akshare",
            "reddit",
            "stocktwits",
            "alpha_vantage",
          ] as const
        ).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setSourceFilter(key)}
            style={{
              padding: "4px 10px",
              borderRadius: 999,
              border: `1px solid ${sourceFilter === key ? "var(--color-chartwell-blue)" : "var(--color-stone-border)"}`,
              background: sourceFilter === key ? "var(--color-sky-tint)" : "var(--surface-cloud-white)",
              color: "var(--color-slate-text)",
              fontSize: 12,
              fontWeight: sourceFilter === key ? 600 : 500,
              cursor: "pointer",
            }}
          >
            {key === "all"
              ? `All (${items.length})`
              : `${SOURCE_LABEL[key]} (${sourceCounts[key] ?? 0})`}
          </button>
        ))}
      </div>

      {fetchedAt && (
        <p style={{ fontSize: 11, color: "var(--color-ash-gray)", margin: "0 0 8px" }} className="mono">
          Fetched {fetchedAt}
        </p>
      )}

      {Object.keys(sourceErrors).length > 0 && (
        <div
          role="status"
          style={{
            marginBottom: "var(--spacing-16)",
            padding: "var(--spacing-12)",
            borderRadius: "var(--radius-md)",
            background: "#fffbeb",
            border: "1px solid #fcd34d",
            fontSize: "var(--text-caption)",
            color: "#92400e",
          }}
        >
          <strong>Some sources failed:</strong>
          <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>
            {Object.entries(sourceErrors).map(([src, msg]) => (
              <li key={src}>
                <span className="mono">{src}</span>: {msg}
              </li>
            ))}
          </ul>
        </div>
      )}

      <ul ref={listRef} style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {visible.map((it, idx) => {
          const c = sentimentColor(it.sentiment);
          const srcKey = it.source ?? "yfinance";
          const src = SOURCE_STYLE[srcKey] ?? SOURCE_STYLE.yfinance;
          return (
            <li
              key={`${srcKey}-${it.link}-${idx}`}
              style={{
                padding: "var(--spacing-16)",
                marginBottom: "var(--spacing-12)",
                background: "var(--surface-cloud-white)",
                borderRadius: "var(--radius-lg)",
                border: "1px solid var(--color-stone-border)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  marginBottom: 6,
                  flexWrap: "wrap",
                }}
              >
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    padding: "2px 8px",
                    borderRadius: 999,
                    background: src.bg,
                    color: src.fg,
                  }}
                >
                  {SOURCE_LABEL[srcKey]}
                </span>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    padding: "2px 8px",
                    borderRadius: 999,
                    background: c.bg,
                    color: c.fg,
                  }}
                >
                  {it.sentiment}
                </span>
                <span style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>
                  {it.publisher}
                  {it.pub_date ? ` · ${it.pub_date}` : ""}
                </span>
              </div>
              <div style={{ fontWeight: 600 }}>{it.title}</div>
              {it.summary && (
                <p style={{ margin: "8px 0 0", color: "var(--color-ash-gray)", fontSize: 14 }}>
                  {it.summary}
                </p>
              )}
              {it.link && (
                <a href={it.link} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>
                  Open link
                </a>
              )}
            </li>
          );
        })}
      </ul>
      {!loading && items.length === 0 && (
        <p style={{ color: "var(--color-ash-gray)", fontSize: "var(--text-caption)" }}>
          Enter a ticker and choose Load. If sources fail, check network access and optional keys (e.g. Alpha Vantage).
        </p>
      )}
    </div>
  );
}
