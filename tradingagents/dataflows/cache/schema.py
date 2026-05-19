"""DDL for the optional TradingAgents data cache (SQLite file or Cloudflare D1).

Tables are namespaced with ``ta_`` to avoid collisions with API history tables.
Keep statements single-statement per entry for Cloudflare D1 HTTP ``/query``.
"""

from __future__ import annotations

DATA_CACHE_BOOTSTRAP_DDLS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS ta_news_items (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        rank INTEGER,
        title TEXT NOT NULL,
        url TEXT,
        content TEXT,
        publish_time TEXT,
        crawl_time TEXT NOT NULL,
        sentiment_score REAL,
        analysis_note TEXT,
        meta_json TEXT
    )
    """.strip(),
    """
    CREATE INDEX IF NOT EXISTS idx_ta_news_crawl
    ON ta_news_items (crawl_time)
    """.strip(),
    """
    CREATE INDEX IF NOT EXISTS idx_ta_news_source
    ON ta_news_items (source_id)
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS ta_stock_bars (
        ticker TEXT NOT NULL,
        bar_date TEXT NOT NULL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL,
        change_pct REAL,
        vendor TEXT NOT NULL DEFAULT 'yfinance',
        PRIMARY KEY (ticker, bar_date, vendor)
    )
    """.strip(),
    """
    CREATE INDEX IF NOT EXISTS idx_ta_stock_ticker_date
    ON ta_stock_bars (ticker, bar_date)
    """.strip(),
)
