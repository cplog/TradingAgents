"""StockTwits: skip or soft-fail non-US symbols (e.g. 6060.HK)."""

import pytest


def test_stocktwits_skips_hk_without_request(monkeypatch):
    from tradingagents.dataflows import stocktwits as st

    called = []

    def _boom(*_a, **_k):
        called.append(True)
        raise AssertionError("should not call StockTwits for .HK")

    monkeypatch.setattr(st, "urlopen", _boom)
    out = st.fetch_stocktwits_feed_items("6060.HK", limit=5)
    assert out == []
    assert called == []


def test_stocktwits_class_shares_still_attempted():
    from tradingagents.dataflows.stocktwits import stocktwits_stream_likely_available

    assert stocktwits_stream_likely_available("BRK.A") is True


def test_stocktwits_messages_placeholder_for_hk():
    from tradingagents.dataflows import stocktwits as st

    msg = st.fetch_stocktwits_messages("6060.HK", limit=5)
    assert "skipped" in msg.lower() or "stocktwits" in msg.lower()
    assert "6060.HK" in msg or "HK" in msg
