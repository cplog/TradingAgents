"""Tests for the Hacker News dataflow module."""

from unittest.mock import patch

import pytest

from tradingagents.dataflows.hackernews import (
    _is_likely_tech_ticker,
    fetch_hackernews_stories,
)


@pytest.mark.unit
class TestIsLikelyTechTicker:
    def test_tech_tickers_match(self):
        assert _is_likely_tech_ticker("AMD") is True
        assert _is_likely_tech_ticker("AI") is True
        assert _is_likely_tech_ticker("CLOUD") is True
        assert _is_likely_tech_ticker("NVIDIA") is True
        assert _is_likely_tech_ticker("DATADOG") is True  # 'DATA' substring

    def test_non_tech_tickers_skip(self):
        assert _is_likely_tech_ticker("JPM") is False
        assert _is_likely_tech_ticker("BP") is False
        assert _is_likely_tech_ticker("601318.SS") is False


@pytest.mark.unit
class TestFetchHackernewsStories:
    def test_skips_non_tech_ticker(self):
        result = fetch_hackernews_stories("JPM")
        assert "skipped" in result.lower()
        assert "JPM" in result

    @patch("tradingagents.dataflows.hackernews.urlopen")
    @patch("tradingagents.dataflows.hackernews._is_likely_tech_ticker")
    def test_fetches_and_formats_stories(self, mock_is_tech, mock_urlopen):
        mock_is_tech.return_value = True
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = (
            b'{"hits": [{'
            b'  "objectID": "123",'
            b'  "title": "Why NVDA is dominating AI training",'
            b'  "url": "https://example.com/nvda",'
            b'  "points": 420,'
            b'  "num_comments": 88,'
            b'  "author": "pg",'
            b'  "created_at_i": 1700000000'
            b'}]}'
        )

        result = fetch_hackernews_stories("NVDA")
        assert "Why NVDA is dominating AI training" in result
        assert "420" in result
        assert "88" in result
        assert "pg" in result
        assert "news.ycombinator.com/item?id=123" in result

    @patch("tradingagents.dataflows.hackernews.urlopen")
    @patch("tradingagents.dataflows.hackernews._is_likely_tech_ticker")
    def test_empty_results(self, mock_is_tech, mock_urlopen):
        mock_is_tech.return_value = True
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = b'{"hits": []}'

        result = fetch_hackernews_stories("NVDA")
        assert "no hacker news stories" in result.lower()
