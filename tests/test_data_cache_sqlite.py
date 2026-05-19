"""Unit tests for TradingAgents data cache (SQLite file backend)."""

from __future__ import annotations

import tempfile

import pytest

from tradingagents.dataflows.cache.repository import (
    ensure_schema_for_backend,
    search_cached_news,
    upsert_news_items,
)


@pytest.mark.unit
def test_sqlite_cache_upsert_and_search():
    with tempfile.TemporaryDirectory() as td:
        cfg = {
            "data_cache_backend": "sqlite",
            "data_cache_dir": td,
            "data_cache_sqlite_filename": "unit_ta_cache.db",
        }
        ensure_schema_for_backend(cfg)
        written = upsert_news_items(
            cfg,
            [
                {
                    "source_id": "demo",
                    "rank": 1,
                    "title": "NVDA supply chain note",
                    "url": "https://example.com/x",
                    "publish_time": "",
                    "crawl_time": "2026-05-17T12:00:00Z",
                    "meta_json": {"probe": True},
                }
            ],
        )
        assert written == 1
        rows = search_cached_news(cfg, "NVDA", 5)
        assert len(rows) == 1
        assert "NVDA" in rows[0]["title"]
