"""Static metadata for the dataflows routing layer.

Category keys align with ``DEFAULT_CONFIG["data_vendors"]`` in
``tradingagents/default_config.py``. Tool method names map to those categories
via ``TOOLS_CATEGORIES``; ``interface.py`` binds each method to concrete vendor
callables in ``VENDOR_METHODS``.
"""

from __future__ import annotations

from typing import TypedDict


class _CategoryInfo(TypedDict):
    description: str
    tools: list[str]


# Tools organized by category (keys = ``data_vendors`` entries).
TOOLS_CATEGORIES: dict[str, _CategoryInfo] = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data",
            "query_cached_ohlcv",
        ],
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators",
        ],
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement",
        ],
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
            "fetch_hot_news_board",
            "search_data_cache_news",
            "get_prediction_market_snapshot",
        ],
    },
    "macro_data": {
        "description": "Macroeconomic indicators (rates, inflation, labor, growth)",
        "tools": [
            "get_macro_data",
        ],
    },
    "prediction_markets": {
        "description": "Market-implied probabilities for forward-looking events",
        "tools": [
            "get_prediction_markets",
        ],
    },
    "options_data": {
        "description": "Options chain data (expirations, strikes, IV, volume, OI)",
        "tools": [
            "get_options_chain",
            "get_options_expirations",
        ],
    },
}

# Order used when merging configured primaries with fallbacks. Per-method entries
# in VENDOR_METHODS that are missing for a tool are skipped when building the chain.
VENDOR_TRY_ORDER: tuple[str, ...] = (
    "yfinance",
    "fred",
    "polymarket",
    "finnhub",
    "google_rss",
    "akshare",
    "alpha_vantage",
    "baostock",
)

VENDOR_LIST: list[str] = list(VENDOR_TRY_ORDER)


def get_category_for_method(method: str) -> str:
    """Return the ``data_vendors`` category that owns ``method``."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")
