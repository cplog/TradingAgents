"""Finnhub free-tier REST helpers (OHLCV candles, company news, general news).

API reference: https://finnhub.io/docs/api
Requires ``FINNHUB_API_KEY`` (free registration).

**Markets:** Company candles and company news work for **US and many international
exchanges**, including **Hong Kong** (e.g. ``6060.HK``). Mainland China ``.SH`` /
``.SZ`` symbols are mapped to Finnhub ``.SS`` / unchanged suffixes as appropriate.
Requires a Finnhub symbol match; if Finnhub returns no data, routing falls back
to other configured news/stock vendors.

BaoStock in this repo is **A-share OHLCV only**. AKShare is wired for **A-share,
HK (``*.HK``), and US** daily bars in ``get_stock_data`` fallbacks.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import requests

from .config import get_config
from .vendor_errors import DataVendorUnavailable

_BASE = "https://finnhub.io/api/v1"
_TIMEOUT = 25.0


def _token() -> str:
    return (os.getenv("FINNHUB_API_KEY") or "").strip()


def _finnhub_symbol(symbol: str) -> str:
    """Map common exchange suffixes to Finnhub tickers (e.g. ``600000.SH`` → ``600000.SS``)."""
    s = symbol.strip().upper()
    if s.endswith(".SH"):
        return s[:-3] + ".SS"
    return s


def get_stock_finnhub(
    symbol: str,
    start_date: str,
    end_date: str,
) -> str:
    """Daily OHLCV + volume (no adjusted column) as CSV with header lines."""
    tok = _token()
    if not tok:
        raise DataVendorUnavailable("finnhub: FINNHUB_API_KEY not set")

    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    # inclusive end day
    end_ts = int((end_dt + timedelta(days=1)).timestamp()) - 1

    sym = _finnhub_symbol(symbol)
    url = f"{_BASE}/stock/candle"
    try:
        r = requests.get(
            url,
            params={
                "symbol": sym,
                "resolution": "D",
                "from": start_ts,
                "to": end_ts,
                "token": tok,
            },
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise DataVendorUnavailable(f"finnhub stock: {exc}") from exc

    if r.status_code == 401:
        raise DataVendorUnavailable("finnhub stock: invalid or missing API key")
    if r.status_code == 429:
        raise DataVendorUnavailable("finnhub stock: rate limited")
    if r.status_code >= 400:
        raise DataVendorUnavailable(f"finnhub stock: HTTP {r.status_code}")

    try:
        payload: dict[str, Any] = r.json()
    except ValueError as exc:
        raise DataVendorUnavailable("finnhub stock: invalid JSON") from exc

    if payload.get("s") == "no_data":
        raise DataVendorUnavailable("finnhub stock: no data for symbol/range")
    if payload.get("s") != "ok" or not payload.get("t"):
        msg = str(payload.get("error") or payload)[:200]
        raise DataVendorUnavailable(f"finnhub stock: {msg}")

    ts_list = payload["t"]
    o = payload.get("o") or []
    h = payload.get("h") or []
    l = payload.get("l") or []
    c = payload.get("c") or []
    v = payload.get("v") or []

    lines = ["Date,Open,High,Low,Close,Volume"]
    for i, t in enumerate(ts_list):
        day = datetime.utcfromtimestamp(int(t)).strftime("%Y-%m-%d")
        if day < start_date or day > end_date:
            continue
        try:
            lines.append(
                f"{day},{o[i]:.4f},{h[i]:.4f},{l[i]:.4f},{c[i]:.4f},{int(v[i])}"
            )
        except (IndexError, TypeError, ValueError):
            continue

    if len(lines) <= 1:
        raise DataVendorUnavailable("finnhub stock: empty after date filter")

    body = "\n".join(lines)
    header = (
        f"# Stock data for {symbol.upper()} from {start_date} to {end_date} (Finnhub)\n"
        f"# Rows: {len(lines) - 1}\n\n"
    )
    return header + body


def get_news_finnhub(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """Company news for a symbol within an inclusive date range."""
    tok = _token()
    if not tok:
        raise DataVendorUnavailable("finnhub news: FINNHUB_API_KEY not set")

    sym = _finnhub_symbol(ticker)
    url = f"{_BASE}/company-news"
    limit = get_config().get("news_article_limit", 20)
    try:
        r = requests.get(
            url,
            params={
                "symbol": sym,
                "from": start_date,
                "to": end_date,
                "token": tok,
            },
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise DataVendorUnavailable(f"finnhub news: {exc}") from exc

    if r.status_code == 401:
        raise DataVendorUnavailable("finnhub news: invalid or missing API key")
    if r.status_code == 429:
        raise DataVendorUnavailable("finnhub news: rate limited")
    if r.status_code >= 400:
        raise DataVendorUnavailable(f"finnhub news: HTTP {r.status_code}")

    try:
        items = r.json()
    except ValueError as exc:
        raise DataVendorUnavailable("finnhub news: invalid JSON") from exc

    if not isinstance(items, list):
        raise DataVendorUnavailable("finnhub news: unexpected response")

    if not items:
        raise DataVendorUnavailable("finnhub news: no articles")

    def _art_day(art: dict) -> str | None:
        raw = art.get("datetime")
        if isinstance(raw, (int, float)):
            return datetime.utcfromtimestamp(int(raw)).strftime("%Y-%m-%d")
        if isinstance(raw, str) and len(raw) >= 10:
            return raw[:10]
        return None

    parts: list[str] = []
    for art in items:
        if len(parts) >= limit:
            break
        if not isinstance(art, dict):
            continue
        day = _art_day(art)
        if day and (day < start_date or day > end_date):
            continue
        headline = str(art.get("headline") or "")
        src = str(art.get("source") or "")
        url_a = str(art.get("url") or "")
        summary = str(art.get("summary") or "")
        parts.append(f"### {headline} ({src}, {day or '?'})\n{summary}\n{url_a}\n")
    if not parts:
        raise DataVendorUnavailable("finnhub news: no articles in date range")
    if not parts:
        raise DataVendorUnavailable("finnhub news: no parseable articles")

    return (
        f"## {ticker} News (Finnhub), {start_date} to {end_date}:\n\n" + "\n".join(parts)
    )


def get_global_news_finnhub(
    curr_date: str,
    look_back_days: int = 7,
    limit: int | None = None,
) -> str:
    """Broad market headlines via Finnhub ``/news`` (category *general*)."""
    tok = _token()
    if not tok:
        raise DataVendorUnavailable("finnhub global news: FINNHUB_API_KEY not set")

    cfg = get_config()
    if limit is None:
        limit = int(cfg.get("global_news_article_limit", 10))

    datetime.strptime(curr_date, "%Y-%m-%d")
    curr = datetime.strptime(curr_date, "%Y-%m-%d")
    start = curr - timedelta(days=look_back_days)

    url = f"{_BASE}/news"
    try:
        r = requests.get(
            url,
            params={"category": "general", "token": tok},
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise DataVendorUnavailable(f"finnhub global news: {exc}") from exc

    if r.status_code == 401:
        raise DataVendorUnavailable("finnhub global news: invalid or missing API key")
    if r.status_code == 429:
        raise DataVendorUnavailable("finnhub global news: rate limited")
    if r.status_code >= 400:
        raise DataVendorUnavailable(f"finnhub global news: HTTP {r.status_code}")

    try:
        items = r.json()
    except ValueError as exc:
        raise DataVendorUnavailable("finnhub global news: invalid JSON") from exc

    if not isinstance(items, list):
        raise DataVendorUnavailable("finnhub global news: unexpected response")

    parts: list[str] = []
    for art in items:
        if len(parts) >= limit:
            break
        if not isinstance(art, dict):
            continue
        headline = str(art.get("headline") or "")
        src = str(art.get("source") or "")
        url_a = str(art.get("url") or "")
        raw_dt = art.get("datetime")
        try:
            if isinstance(raw_dt, (int, float)):
                pub = datetime.utcfromtimestamp(int(raw_dt))
            else:
                continue
        except (OverflowError, OSError, ValueError):
            continue
        if pub.date() < start.date() or pub.date() > curr.date():
            continue
        parts.append(f"### {headline} ({src})\n{url_a}\n")

    if not parts:
        raise DataVendorUnavailable("finnhub global news: no items in window")

    return (
        f"## Global Market News (Finnhub), {start.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + "\n".join(parts)
    )
