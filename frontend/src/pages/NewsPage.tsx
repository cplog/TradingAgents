import { useAutoAnimate } from "@formkit/auto-animate/react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageFrame, PageHeader } from "../components/PageFrame";
import { Pressable } from "../components/Pressable";
import { SentimentTimelineChart } from "../components/charts/SentimentTimelineChart";
import { fetchNews, fetchTopics, type NewsItem, type NewsSource, type TopicSummary } from "../api";
import { topicPath } from "../navigation/routes";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

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

export function NewsPage() {
  const [listRef] = useAutoAnimate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tickerFromUrl = searchParams.get("ticker")?.trim().toUpperCase() || "AAPL";
  const [ticker, setTicker] = useState(tickerFromUrl);
  const [items, setItems] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [sourceFilter, setSourceFilter] = useState<"all" | NewsSource>("all");
  const [sourceErrors, setSourceErrors] = useState<Record<string, string>>({});
  const [fetchedAt, setFetchedAt] = useState<string | null>(null);
  const [relatedTopics, setRelatedTopics] = useState<TopicSummary[]>([]);

  useEffect(() => {
    void fetchTopics()
      .then((res) => setRelatedTopics(res.topics.slice(0, 8)))
      .catch(() => setRelatedTopics([]));
  }, []);

  useDocumentTitle(ticker.trim() ? `${ticker.trim().toUpperCase()} — News` : "News");

  async function load() {
    setLoading(true);
    const trimmed = ticker.trim().toUpperCase();
    if (trimmed) {
      const next = new URLSearchParams(searchParams);
      next.set("ticker", trimmed);
      setSearchParams(next, { replace: true });
    }
    try {
      const r = await fetchNews(trimmed, 50);
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
    <PageFrame>
      <PageHeader
        title="News and sentiment"
        description="Merged streams from Yahoo, Finnhub, Google RSS, AKShare, Alpha Vantage, Reddit, and StockTwits."
        meta={<AppBreadcrumbs items={[{ label: "News" }]} />}
      />
      <p className="page-lead">
        Raw streams merged: <strong>Yahoo ticker news</strong>, <strong>Yahoo macro search</strong>,{" "}
        <strong>Finnhub</strong>, <strong>Google RSS</strong>, <strong>AKShare</strong>,{" "}
        <strong>Alpha Vantage</strong> when <span className="mono">ALPHA_VANTAGE_API_KEY</span> is set, plus{" "}
        <strong>Reddit</strong> and <strong>StockTwits</strong>. Sentiment uses keywords and source labels — not an LLM.
      </p>
      <div className="ui-form-row ui-form-row--stretch">
        <input
          className="ui-input"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          placeholder="Ticker"
        />
        <Pressable
          className="ui-btn-primary"
          disabled={loading}
          onClick={() => void load().catch((e) => alert(String(e)))}
        >
          Load
        </Pressable>
      </div>

      {items.length > 0 && (
        <>
          <p className="ui-label" style={{ margin: "var(--spacing-16) 0 var(--spacing-8)" }}>
            Sentiment trend (WMS-style index)
          </p>
          <SentimentTimelineChart items={items} />
        </>
      )}

      <div className="ui-form-row" style={{ margin: "var(--spacing-16) 0" }}>
        <span className="ui-label" style={{ margin: 0 }}>
          Source
        </span>
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
            className={`ui-chip ui-chip--source${sourceFilter === key ? " ui-chip--active" : ""}`}
            onClick={() => setSourceFilter(key)}
          >
            {key === "all"
              ? `All (${items.length})`
              : `${SOURCE_LABEL[key]} (${sourceCounts[key] ?? 0})`}
          </button>
        ))}
      </div>

      {relatedTopics.length > 0 ? (
        <div className="ui-form-row" style={{ margin: "var(--spacing-12) 0" }}>
          <span className="ui-label" style={{ margin: 0 }}>
            Related themes
          </span>
          {relatedTopics.map((t) => (
            <Link key={t.id} to={topicPath(t.id)} className="ui-chip ui-chip--source">
              {t.label}
            </Link>
          ))}
        </div>
      ) : null}

      {fetchedAt && (
        <p className="mono" style={{ fontSize: 11, color: "var(--color-ash-gray)", margin: "0 0 8px" }}>
          Fetched {fetchedAt}
        </p>
      )}

      {Object.keys(sourceErrors).length > 0 && (
        <div className="notice--warn" role="status">
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

      <ul ref={listRef} className="news-list">
        {visible.map((it, idx) => {
          const srcKey = it.source ?? "yfinance";
          const sentimentClass =
            it.sentiment === "bullish"
              ? "status-chip--bullish"
              : it.sentiment === "bearish"
                ? "status-chip--bearish"
                : "status-chip--neutral";
          return (
            <li key={`${srcKey}-${it.link}-${idx}`} className="news-card">
              <div className="news-card__meta">
                <span className="status-chip status-chip--info">{SOURCE_LABEL[srcKey]}</span>
                <span className={`status-chip ${sentimentClass}`}>{it.sentiment}</span>
                <span style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>
                  {it.publisher}
                  {it.pub_date ? ` · ${it.pub_date}` : ""}
                </span>
              </div>
              <div className="news-card__title">{it.title}</div>
              {it.summary && <p className="news-card__summary">{it.summary}</p>}
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
    </PageFrame>
  );
}
