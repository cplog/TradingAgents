"""Ticker news feed for the UX module: all configured raw news sources."""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List

import yfinance as yf

from tradingagents.dataflows.alpha_vantage_news import fetch_alpha_vantage_news_feed_items
from tradingagents.dataflows.reddit import fetch_reddit_feed_items
from tradingagents.dataflows.stockstats_utils import yf_retry
from tradingagents.dataflows.stocktwits import fetch_stocktwits_feed_items
from tradingagents.dataflows.yfinance_news import _extract_article_data, fetch_macro_news_feed_items

from api.models import NewsFeedResponse, NewsItem
from api.tickers import normalize_ticker

logger = logging.getLogger(__name__)

_BULLISH = re.compile(
    r"\b(rally|surge|gain|bull|upgrade|beat|growth|optim|strong|outperform|buy)\b",
    re.I,
)
_BEARISH = re.compile(
    r"\b(crash|plunge|bear|downgrade|miss|weak|lawsuit|selloff|cut|loss|sell[- ]?off)\b",
    re.I,
)


def _sentiment_from_text(title: str, summary: str) -> tuple[str, float]:
    text = f"{title}\n{summary}"
    b = len(_BULLISH.findall(text))
    s = len(_BEARISH.findall(text))
    if b > s:
        return "bullish", min(0.9, 0.35 + 0.15 * (b - s))
    if s > b:
        return "bearish", max(-0.9, -0.35 - 0.15 * (s - b))
    return "neutral", 0.0


def _sentiment_from_stocktwits_basic(basic: str | None) -> tuple[str, float]:
    if basic == "Bullish":
        return "bullish", 0.45
    if basic == "Bearish":
        return "bearish", -0.45
    return "neutral", 0.0


def _sentiment_from_alpha_vantage(label: str, score: float) -> tuple[str, float]:
    lab = (label or "").lower()
    s = max(-1.0, min(1.0, score))
    if "bull" in lab:
        return "bullish", s if abs(s) > 0.02 else 0.42
    if "bear" in lab:
        return "bearish", s if abs(s) > 0.02 else -0.42
    return "neutral", s


def _items_yfinance(ticker: str, limit: int, days: int) -> List[NewsItem]:
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    items: List[NewsItem] = []
    stock = yf.Ticker(ticker)
    articles = yf_retry(lambda: stock.get_news(count=max(limit, 5)))
    if not articles:
        return []
    for article in articles[:limit]:
        data = _extract_article_data(article)
        pub = data.get("pub_date")
        pub_s = None
        if pub:
            try:
                naive = pub.replace(tzinfo=None)
                pub_s = naive.isoformat() + "Z"
                if naive < start:
                    continue
            except (AttributeError, ValueError):
                pub_s = str(pub)
        label, score = _sentiment_from_text(
            str(data.get("title", "")), str(data.get("summary", ""))
        )
        sector_tags: List[str] = []
        title_l = str(data.get("title", "")).lower()
        if "fed" in title_l or "rate" in title_l:
            sector_tags.append("macro")
        items.append(
            NewsItem(
                title=str(data.get("title", "Untitled")),
                summary=str(data.get("summary", "")),
                publisher=str(data.get("publisher", "")),
                link=str(data.get("link", "")),
                pub_date=pub_s,
                ticker=ticker,
                sentiment=label,  # type: ignore[arg-type]
                sentiment_score=score,
                sector_tags=sector_tags,
                source="yfinance",
            )
        )
    return items


def fetch_news_feed(
    ticker: str,
    *,
    limit: int = 50,
    days: int = 14,
) -> NewsFeedResponse:
    """Merge Yahoo ticker headlines, Yahoo macro search, Alpha Vantage (if key set), Reddit, StockTwits."""
    norm = normalize_ticker(ticker)
    source_errors: Dict[str, str] = {}
    per_source_cap = max(limit, 15)
    end = datetime.utcnow()
    curr_day = end.strftime("%Y-%m-%d")
    start_day = (end - timedelta(days=days)).strftime("%Y-%m-%d")

    items: List[NewsItem] = []

    try:
        items.extend(_items_yfinance(norm, min(per_source_cap, 40), days))
    except Exception as exc:
        logger.exception("yfinance news failed for %s: %s", norm, exc)
        source_errors["yfinance"] = str(exc)[:300]

    try:
        macro_limit = min(15, max(5, per_source_cap // 3))
        for row in fetch_macro_news_feed_items(
            curr_day,
            look_back_days=min(days, 14),
            limit=macro_limit,
        ):
            title = str(row.get("title") or "")
            summary = str(row.get("summary") or "")
            label, score = _sentiment_from_text(title, summary)
            items.append(
                NewsItem(
                    title=title or "Untitled",
                    summary=summary,
                    publisher=str(row.get("publisher") or ""),
                    link=str(row.get("link") or ""),
                    pub_date=row.get("pub_date"),
                    ticker=norm,
                    sentiment=label,  # type: ignore[arg-type]
                    sentiment_score=score,
                    sector_tags=["macro"],
                    source="yfinance_macro",
                )
            )
    except Exception as exc:
        logger.exception("Yahoo macro news failed for %s: %s", norm, exc)
        source_errors["yfinance_macro"] = str(exc)[:300]

    if os.getenv("ALPHA_VANTAGE_API_KEY"):
        try:
            cap = min(25, per_source_cap)
            for row in fetch_alpha_vantage_news_feed_items(norm, start_day, curr_day)[:cap]:
                label, score = _sentiment_from_alpha_vantage(
                    str(row.get("overall_sentiment_label") or ""),
                    float(row.get("overall_sentiment_score") or 0.0),
                )
                items.append(
                    NewsItem(
                        title=str(row.get("title") or "Untitled"),
                        summary=str(row.get("summary") or ""),
                        publisher=str(row.get("publisher") or "Alpha Vantage"),
                        link=str(row.get("link") or ""),
                        pub_date=row.get("pub_date"),
                        ticker=norm,
                        sentiment=label,  # type: ignore[arg-type]
                        sentiment_score=score,
                        sector_tags=[],
                        source="alpha_vantage",
                    )
                )
        except Exception as exc:
            logger.exception("Alpha Vantage news failed for %s: %s", norm, exc)
            source_errors["alpha_vantage"] = str(exc)[:300]

    try:
        for row in fetch_reddit_feed_items(
            norm,
            limit_per_sub=max(3, min(8, per_source_cap // 3)),
        ):
            title = str(row.get("title") or "")
            summary = str(row.get("summary") or "")
            label, score = _sentiment_from_text(title, summary)
            items.append(
                NewsItem(
                    title=title,
                    summary=summary,
                    publisher=str(row.get("publisher") or ""),
                    link=str(row.get("link") or ""),
                    pub_date=row.get("pub_date"),
                    ticker=norm,
                    sentiment=label,  # type: ignore[arg-type]
                    sentiment_score=score,
                    sector_tags=[],
                    source="reddit",
                )
            )
    except Exception as exc:
        logger.exception("Reddit news failed for %s: %s", norm, exc)
        source_errors["reddit"] = str(exc)[:300]

    try:
        raw_st = fetch_stocktwits_feed_items(norm, limit=min(35, per_source_cap))
        for row in raw_st:
            basic = row.get("sentiment_basic")
            label, score = _sentiment_from_stocktwits_basic(
                basic if isinstance(basic, str) else None
            )
            items.append(
                NewsItem(
                    title=str(row.get("title") or ""),
                    summary=str(row.get("summary") or ""),
                    publisher=str(row.get("publisher") or "StockTwits"),
                    link=str(row.get("link") or ""),
                    pub_date=row.get("pub_date"),
                    ticker=norm,
                    sentiment=label,  # type: ignore[arg-type]
                    sentiment_score=score,
                    sector_tags=[],
                    source="stocktwits",
                )
            )
    except Exception as exc:
        logger.exception("StockTwits news failed for %s: %s", norm, exc)
        source_errors["stocktwits"] = str(exc)[:300]

    items.sort(key=lambda x: x.pub_date or "", reverse=True)
    merged = items[: max(1, min(limit, 200))]

    return NewsFeedResponse(
        ticker=norm,
        items=merged,
        fetched_at=datetime.utcnow(),
        source_errors=source_errors,
    )
