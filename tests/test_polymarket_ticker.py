"""Tests for the ticker-specific Polymarket fetcher."""

from unittest.mock import patch

import pytest

from tradingagents.dataflows.hot_board import fetch_polymarket_for_ticker


def _market(
    question: str,
    slug: str,
    *,
    closed: bool = False,
    archived: bool = False,
    volume: str = "500000",
    liquidity: str = "100000",
    outcomes: list[str] | None = None,
    outcome_prices: list[float | str] | None = None,
    description: str = "",
) -> dict:
    # The live ``/public-search`` endpoint returns outcomes/outcomePrices as
    # JSON-encoded strings, so the default fixtures mimic that shape.
    outcomes_list = outcomes or ["Yes", "No"]
    prices_list = outcome_prices or ["0.72", "0.28"]
    import json

    return {
        "id": slug,
        "question": question,
        "description": description,
        "slug": slug,
        "volume": volume,
        "liquidity": liquidity,
        "closed": closed,
        "archived": archived,
        "outcomes": json.dumps(outcomes_list),
        "outcomePrices": json.dumps(prices_list),
    }


@pytest.mark.unit
class TestFetchPolymarketForTicker:
    @patch("tradingagents.dataflows.hot_board.requests.get")
    def test_filters_by_ticker_keyword(self, mock_get):
        mock_get.return_value.json.return_value = {
            "events": [
                {
                    "title": "NVDA earnings",
                    "description": "Nvidia earnings",
                    "ticker": "nvda-earnings-q3",
                    "slug": "nvda-earnings-q3",
                    "markets": [
                        _market("Will NVDA beat earnings in Q3?", "nvda-earnings-q3"),
                    ],
                },
                {
                    "title": "Tesla stock price",
                    "description": "Tesla stock price",
                    "ticker": "tsla-300",
                    "slug": "tsla-300",
                    "markets": [
                        _market("Will TSLA hit $300 by year end?", "tsla-300"),
                    ],
                },
            ]
        }
        mock_get.return_value.raise_for_status = lambda: None

        result = fetch_polymarket_for_ticker("NVDA")
        assert "NVDA" in result
        assert "Will NVDA beat earnings in Q3?" in result
        assert "Yes=72%" in result or "Yes=72.0%" in result
        assert "TSLA" not in result

    @patch("tradingagents.dataflows.hot_board.requests.get")
    def test_no_matches_returns_placeholder(self, mock_get):
        mock_get.return_value.json.return_value = {
            "events": [
                {
                    "title": "Will it rain in London?",
                    "description": "Weather",
                    "ticker": "london-rain",
                    "slug": "london-rain",
                    "markets": [
                        _market("Will it rain in London?", "london-rain"),
                    ],
                },
            ]
        }
        mock_get.return_value.raise_for_status = lambda: None

        result = fetch_polymarket_for_ticker("NVDA")
        assert "no active polymarket markets matched" in result.lower()

    @patch("tradingagents.dataflows.hot_board.requests.get")
    def test_closed_and_archived_markets_are_excluded(self, mock_get):
        mock_get.return_value.json.return_value = {
            "events": [
                {
                    "title": "NVDA event",
                    "ticker": "nvda-event",
                    "slug": "nvda-event",
                    "markets": [
                        _market("Active NVDA market", "nvda-active"),
                        _market("Closed NVDA market", "nvda-closed", closed=True),
                        _market("Archived NVDA market", "nvda-archived", archived=True),
                    ],
                },
            ]
        }
        mock_get.return_value.raise_for_status = lambda: None

        result = fetch_polymarket_for_ticker("NVDA")
        assert "Active NVDA market" in result
        assert "Closed NVDA market" not in result
        assert "Archived NVDA market" not in result

    @patch("tradingagents.dataflows.hot_board.requests.get")
    def test_api_error_graceful(self, mock_get):
        mock_get.side_effect = Exception("Connection timeout")

        result = fetch_polymarket_for_ticker("NVDA")
        assert "failed" in result.lower()
