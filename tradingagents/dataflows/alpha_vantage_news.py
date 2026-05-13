from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from .alpha_vantage_common import _make_api_request, format_datetime_for_api


def _parse_av_time_published(raw: str | None) -> str | None:
    if not raw or not isinstance(raw, str) or len(raw) < 15:
        return None
    try:
        dt = datetime.strptime(raw[:15], "%Y%m%dT%H%M%S")
        return dt.isoformat() + "Z"
    except ValueError:
        return None


def fetch_alpha_vantage_news_feed_items(
    ticker: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    """NEWS_SENTIMENT feed for ``tickers=``; empty if ``ALPHA_VANTAGE_API_KEY`` is unset."""
    if not os.getenv("ALPHA_VANTAGE_API_KEY"):
        return []

    raw = get_news(ticker, start_date, end_date)
    if not isinstance(raw, str):
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, dict):
        return []

    if data.get("Error Message"):
        raise ValueError(str(data["Error Message"])[:300])
    note = data.get("Note") or data.get("Information")
    if note and not data.get("feed"):
        raise ValueError(str(note)[:300])

    feed = data.get("feed")
    if not isinstance(feed, list):
        return []

    out: list[dict[str, Any]] = []
    for article in feed:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title") or "")
        summary = str(article.get("summary") or "")
        url = str(article.get("url") or "")
        publisher = str(
            article.get("source")
            or article.get("source_domain")
            or article.get("category_within_source")
            or "Alpha Vantage"
        )
        pub_date = _parse_av_time_published(
            article.get("time_published")
            if isinstance(article.get("time_published"), str)
            else None
        )

        score_raw = article.get("overall_sentiment_score")
        try:
            score = float(score_raw) if score_raw is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0
        label = str(article.get("overall_sentiment_label") or "")

        out.append(
            {
                "title": title,
                "summary": summary,
                "publisher": publisher,
                "link": url,
                "pub_date": pub_date,
                "overall_sentiment_score": max(-1.0, min(1.0, score)),
                "overall_sentiment_label": label,
            }
        )
    return out


def get_news(ticker, start_date, end_date) -> dict[str, str] | str:
    """Returns live and historical market news & sentiment data from premier news outlets worldwide.

    Covers stocks, cryptocurrencies, forex, and topics like fiscal policy, mergers & acquisitions, IPOs.

    Args:
        ticker: Stock symbol for news articles.
        start_date: Start date for news search.
        end_date: End date for news search.

    Returns:
        Dictionary containing news sentiment data or JSON string.
    """

    params = {
        "tickers": ticker,
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(end_date),
    }

    return _make_api_request("NEWS_SENTIMENT", params)

def get_global_news(curr_date, look_back_days: int = 7, limit: int = 50) -> dict[str, str] | str:
    """Returns global market news & sentiment data without ticker-specific filtering.

    Covers broad market topics like financial markets, economy, and more.

    Args:
        curr_date: Current date in yyyy-mm-dd format.
        look_back_days: Number of days to look back (default 7).
        limit: Maximum number of articles (default 50).

    Returns:
        Dictionary containing global news sentiment data or JSON string.
    """
    from datetime import datetime, timedelta

    # Calculate start date
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    params = {
        "topics": "financial_markets,economy_macro,economy_monetary",
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(curr_date),
        "limit": str(limit),
    }

    return _make_api_request("NEWS_SENTIMENT", params)


def get_insider_transactions(symbol: str) -> dict[str, str] | str:
    """Returns latest and historical insider transactions by key stakeholders.

    Covers transactions by founders, executives, board members, etc.

    Args:
        symbol: Ticker symbol. Example: "IBM".

    Returns:
        Dictionary containing insider transaction data or JSON string.
    """

    params = {
        "symbol": symbol,
    }

    return _make_api_request("INSIDER_TRANSACTIONS", params)