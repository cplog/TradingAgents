"""Tests for the ticker-specific Polymarket fetcher."""

from unittest.mock import patch

import pytest

from tradingagents.dataflows.hot_board import fetch_polymarket_for_ticker


@pytest.mark.unit
class TestFetchPolymarketForTicker:
    @patch("tradingagents.dataflows.hot_board.requests.get")
    def test_filters_by_ticker_keyword(self, mock_get):
        mock_get.return_value.json.return_value = [
            {
                "question": "Will NVDA beat earnings in Q3?",
                "description": "Nvidia earnings",
                "slug": "nvda-earnings-q3",
                "volume": "500000",
                "liquidity": "100000",
                "outcomes": ["Yes", "No"],
                "outcomePrices": [0.72, 0.28],
            },
            {
                "question": "Will TSLA hit $300 by year end?",
                "description": "Tesla stock price",
                "slug": "tsla-300",
                "volume": "200000",
                "liquidity": "50000",
                "outcomes": ["Yes", "No"],
                "outcomePrices": [0.45, 0.55],
            },
        ]
        mock_get.return_value.raise_for_status = lambda: None

        result = fetch_polymarket_for_ticker("NVDA")
        assert "NVDA" in result
        assert "Will NVDA beat earnings in Q3?" in result
        assert "Yes=72%" in result or "Yes=72.0%" in result
        assert "TSLA" not in result

    @patch("tradingagents.dataflows.hot_board.requests.get")
    def test_no_matches_returns_placeholder(self, mock_get):
        mock_get.return_value.json.return_value = [
            {
                "question": "Will it rain in London?",
                "description": "Weather",
                "slug": "london-rain",
            },
        ]
        mock_get.return_value.raise_for_status = lambda: None

        result = fetch_polymarket_for_ticker("NVDA")
        assert "no active polymarket markets matched" in result.lower()

    @patch("tradingagents.dataflows.hot_board.requests.get")
    def test_api_error_graceful(self, mock_get):
        mock_get.side_effect = Exception("Connection timeout")

        result = fetch_polymarket_for_ticker("NVDA")
        assert "failed" in result.lower()
