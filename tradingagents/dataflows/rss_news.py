"""Company / macro-oriented RSS (Google News search feeds).

Feeds are fetched over HTTPS without an API key. Results are subject to
`Google News <https://news.google.com/>`_ feed terms (personal/non-commercial
feed-reader use per their RSS copyright notice). Use for research-style
workflows, not high-volume commercial scraping.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from .config import get_config
from .vendor_errors import DataVendorUnavailable

_UA = "TradingAgents/0.2 (+https://github.com/TauricResearch/TradingAgents)"


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _parse_rss_items(xml_bytes: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    out: list[dict[str, Any]] = []
    for item in root.iter():
        if _local_tag(item.tag) != "item":
            continue
        title = link = pub_s = ""
        for child in item:
            t = _local_tag(child.tag)
            if t == "title" and child.text:
                title = child.text.strip()
            elif t == "link" and child.text:
                link = child.text.strip()
            elif t == "pubDate" and child.text:
                pub_s = child.text.strip()
        if title:
            out.append({"title": title, "link": link, "pubDate": pub_s})
    return out


def _pub_to_date(pub: str) -> date | None:
    if not pub:
        return None
    try:
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt.date()
    except (TypeError, ValueError):
        return None


def _fetch_rss(url: str, timeout: float = 20.0) -> bytes:
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/rss+xml"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as exc:
        raise DataVendorUnavailable(f"RSS fetch failed: {exc}") from exc


def get_news_google_rss(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """Headlines from a Google News RSS search for ``ticker`` + stock context."""
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")
    lo = datetime.strptime(start_date, "%Y-%m-%d").date()
    hi = datetime.strptime(end_date, "%Y-%m-%d").date()
    limit = int(get_config().get("news_article_limit", 20))

    q = quote_plus(f"{ticker.strip()} stock OR {ticker.strip()} shares")
    url = f"https://news.google.com/rss/search?q={q}&hl=en&gl=US&ceid=US:en"
    raw = _fetch_rss(url)
    items = _parse_rss_items(raw)
    parts: list[str] = []
    seen: set[str] = set()
    for it in items:
        if len(parts) >= limit:
            break
        pd = _pub_to_date(it.get("pubDate") or "")
        if pd is not None and (pd < lo or pd > hi):
            continue
        key = (it.get("link") or "") + "\0" + (it.get("title") or "")
        if key in seen:
            continue
        seen.add(key)
        title = it.get("title") or ""
        link = it.get("link") or ""
        line = f"### {title}"
        if pd:
            line += f"\n_{pd.isoformat()}_"
        if link:
            line += f"\n{link}"
        parts.append(line)

    if not parts:
        raise DataVendorUnavailable("google_rss news: no articles in window")

    return (
        f"## {ticker} News (Google News RSS), {start_date} to {end_date}\n\n"
        + "\n\n".join(parts)
    )


def get_global_news_google_rss(
    curr_date: str,
    look_back_days: int = 7,
    limit: int | None = None,
) -> str:
    """Merge Google News RSS hits for each configured ``global_news_queries`` row."""
    cfg = get_config()
    if limit is None:
        limit = int(cfg.get("global_news_article_limit", 10))
    queries = cfg.get("global_news_queries") or []
    if not isinstance(queries, list) or not queries:
        raise DataVendorUnavailable("google_rss global: no global_news_queries in config")

    datetime.strptime(curr_date, "%Y-%m-%d")
    hi = datetime.strptime(curr_date, "%Y-%m-%d").date()
    lo = hi - timedelta(days=int(look_back_days))

    collected: list[tuple[date | None, str, str, str]] = []
    for i, query in enumerate(queries):
        if not isinstance(query, str) or not query.strip():
            continue
        if i > 0:
            time.sleep(0.35)
        q = quote_plus(query.strip())
        url = f"https://news.google.com/rss/search?q={q}&hl=en&gl=US&ceid=US:en"
        try:
            raw = _fetch_rss(url)
        except DataVendorUnavailable:
            continue
        for it in _parse_rss_items(raw):
            pd = _pub_to_date(it.get("pubDate") or "")
            if pd is not None and (pd < lo or pd > hi):
                continue
            title = (it.get("title") or "").strip()
            link = (it.get("link") or "").strip()
            if not title:
                continue
            collected.append((pd, query.strip(), title, link))

    collected.sort(key=lambda x: (x[0] or date.min), reverse=True)
    parts: list[str] = []
    seen: set[str] = set()
    for pd, qsrc, title, link in collected:
        if len(parts) >= limit:
            break
        key = link + "\0" + title
        if key in seen:
            continue
        seen.add(key)
        line = f"### {title}\n_Query: {qsrc}_"
        if pd:
            line += f"\n_{pd.isoformat()}_"
        if link:
            line += f"\n{link}"
        parts.append(line)

    if not parts:
        raise DataVendorUnavailable("google_rss global: no articles in window")

    return (
        f"## Global market news (Google News RSS), {lo.isoformat()} to {curr_date}\n\n"
        + "\n\n".join(parts)
    )
