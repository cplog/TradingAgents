"""Tavily client tests."""

from __future__ import annotations

import pytest

from api.tavily import (
    TavilyAuthError,
    TavilyRequestError,
    get_tavily_daily_cap,
    search,
)


@pytest.mark.unit
def test_get_tavily_daily_cap_default(monkeypatch):
    monkeypatch.delenv("TAVILY_DAILY_CAP", raising=False)
    assert get_tavily_daily_cap() == 100


@pytest.mark.unit
def test_search_missing_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(TavilyAuthError):
        search("AI stocks")


@pytest.mark.unit
def test_search_success(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    class FakeResp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "results": [
                    {"title": "NVDA surge", "url": "https://example.com/nvda", "content": "NVIDIA leads AI"},
                ]
            }

        text = ""

        @staticmethod
        def raise_for_status():
            return None

    monkeypatch.setattr("api.tavily.requests.post", lambda *a, **k: FakeResp())
    rows = search("nvidia ai")
    assert len(rows) == 1
    assert rows[0]["title"] == "NVDA surge"


@pytest.mark.unit
def test_search_http_error(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    class FakeResp:
        status_code = 500
        text = "server error"

        @staticmethod
        def raise_for_status():
            return None

    monkeypatch.setattr("api.tavily.requests.post", lambda *a, **k: FakeResp())
    with pytest.raises(TavilyRequestError):
        search("fail")
