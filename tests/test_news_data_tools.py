from __future__ import annotations

import pytest

from tradingagents.agents.utils import news_data_tools


@pytest.mark.unit
def test_get_news_returns_vendor_output(monkeypatch):
    monkeypatch.setattr(
        news_data_tools,
        "route_to_vendor",
        lambda method, ticker, start, end: "## News OK",
    )

    out = news_data_tools.get_news.func("AAPL", "2026-05-01", "2026-05-02")
    assert out == "## News OK"


@pytest.mark.unit
def test_get_news_fails_open_when_all_vendors_unavailable(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise RuntimeError(
            "No available vendor for 'get_news': ALPHA_VANTAGE_API_KEY environment variable is not set."
        )

    monkeypatch.setattr(news_data_tools, "route_to_vendor", _raise)

    out = news_data_tools.get_news.func("NEXN", "2026-05-31", "2026-06-01")
    assert "## News unavailable" in out
    assert "NEXN" in out
    assert "Continuing analysis with other signals" in out

