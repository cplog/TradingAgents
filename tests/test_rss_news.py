"""Unit tests for RSS news helpers (no network)."""

import pytest

from tradingagents.dataflows import rss_news


@pytest.mark.unit
def test_parse_rss_items_extracts_titles():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
    <item><title>Hello &amp; Co</title><link>http://example.com/a</link>
    <pubDate>Mon, 12 May 2025 10:00:00 GMT</pubDate></item>
    </channel></rss>"""
    items = rss_news._parse_rss_items(xml)
    assert len(items) == 1
    assert items[0]["title"] == "Hello & Co"
    assert "example.com" in items[0]["link"]


@pytest.mark.unit
def test_pub_to_date_rfc2822():
    d = rss_news._pub_to_date("Thu, 14 May 2026 11:05:06 GMT")
    assert d is not None
    assert d.year == 2026
    assert d.month == 5


@pytest.mark.unit
def test_get_news_google_rss_filters_by_date(monkeypatch):
    xml = b"""<?xml version="1.0"?><rss version="2.0"><channel>
    <item><title>Old</title><link>http://x/1</link><pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item>
    <item><title>New</title><link>http://x/2</link><pubDate>Mon, 12 May 2025 12:00:00 GMT</pubDate></item>
    </channel></rss>"""

    def fake_fetch(url: str, timeout: float = 20.0):
        return xml

    monkeypatch.setattr(rss_news, "_fetch_rss", fake_fetch)
    monkeypatch.setattr(
        rss_news,
        "get_config",
        lambda: {"news_article_limit": 10},
    )
    out = rss_news.get_news_google_rss("TEST", "2025-05-10", "2025-05-14")
    assert "New" in out
    assert "Old" not in out
    assert "Google News RSS" in out
