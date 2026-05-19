"""Optional persisted news/stock cache: local SQLite or Cloudflare D1."""

from tradingagents.dataflows.cache.repository import (
    cache_status_message,
    ensure_schema_for_backend,
    fetch_cached_stock_bars,
    maybe_autocache_stock_bars_from_payload,
    search_cached_news,
    upsert_news_items,
    upsert_stock_bars,
)

__all__ = [
    "cache_status_message",
    "ensure_schema_for_backend",
    "fetch_cached_stock_bars",
    "maybe_autocache_stock_bars_from_payload",
    "search_cached_news",
    "upsert_news_items",
    "upsert_stock_bars",
]
