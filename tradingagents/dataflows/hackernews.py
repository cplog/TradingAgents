"""Hacker News Algolia search fetcher for ticker-specific stories.

Uses the public Algolia Search API (``hn.algolia.com``) which requires no
API key and has generous rate limits.  Developer-centric sentiment is a
leading indicator for tech / SaaS / infrastructure tickers (NVDA, AMD,
cloud names, etc.).

Returns formatted plaintext blocks ready for prompt injection.  Degrades
gracefully on any HTTP or parse failure.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_API = "https://hn.algolia.com/api/v1/search?query={q}&tags=story&numericFilters=created_at_i>{ts}"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"

# Tech-centric tickers where HN signal is historically strongest.
# Used as a lightweight heuristic to skip the HTTP call for tickers where
# HN discussion is vanishingly rare (e.g. Chinese property developers).
_HN_RELEVANT_KEYWORDS = frozenset({
    "AI", "GPU", "CHIP", "SEMICONDUCTOR", "SOFTWARE", "SAAS", "CLOUD",
    "DATACENTER", "SERVER", "CRYPTO", "BLOCKCHAIN", "FINTECH",
    "TESLA", "NVIDIA", "NVDA", "APPLE", "AAPL", "GOOGLE", "GOOGL", "ALPHABET",
    "AMAZON", "AMZN", "META", "MICROSOFT", "MSFT",
    "NETFLIX", "NFLX", "SPOTIFY", "SPOT", "UBER", "AIRBNB", "ABNB",
    "SNOWFLAKE", "SNOW", "PALANTIR", "PLTR",
    "AMD", "INTEL", "INTC", "QUALCOMM", "QCOM", "BROADCOM", "AVGO",
    "MICRON", "MU", "MARVELL", "MRVL",
    "CRDO", "VST", "OKLO", "COREWEAVE", "DATABRICKS",
    "SALESFORCE", "CRM", "ORACLE", "ORCL", "SHOPIFY", "SHOP",
    "BLOCK", "SQ", "PAYPAL", "PYPL", "COINBASE", "COIN",
    "DATADOG", "DDOG", "CROWDSTRIKE", "CRWD", "CLOUDFLARE", "NET",
    "FASTLY", "FSLY", "OKTA", "ZOOM", "ZM", "DOCUSIGN", "DOCU",
    "UNITY", "U", "ROBLOX", "RBLX",
    "LYFT", "DOORDASH", "DASH", "ROBINHOOD", "HOOD",
    "SOFI", "AFFIRM", "AFRM", "RIVIAN", "RIVN", "LUCID", "LCID",
    "NIO", "XPENG", "XPEV", "LI", "BIDU", "BAIDU",
    "ALIBABA", "BABA", "JD", "PDD", "TENCENT", "TCEHY",
    "NETEASE", "NTES", "SEA", "SE", "GRAB", "GRAB",
    "GITLAB", "GTLB", "SENTINELONE", "S", "MONGODB", "MDB",
    "CONFLUENT", "CFLT", "CEG",
})


def _is_likely_tech_ticker(ticker: str) -> bool:
    """Quick heuristic: does the ticker or a common alias look tech-related?"""
    t = ticker.strip().upper()
    if t in _HN_RELEVANT_KEYWORDS:
        return True
    # Simple substring match against a few patterns
    for kw in ("AI", "TECH", "SOFT", "CHIP", "CLOUD", "DATA", "NET"):
        if kw in t:
            return True
    return False


def _epoch_seconds(days_back: int) -> int:
    return int(time.time()) - days_back * 86400


def _fetch_hn_items(
    query: str,
    from_ts: int,
    limit: int,
    timeout: float,
) -> list[dict]:
    url = _API.format(q=quote(query, safe=""), ts=from_ts)
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("HN fetch failed for %r: %s", query, exc)
        return []
    hits = payload.get("hits") or []
    out: list[dict] = []
    seen: set[str] = set()
    for h in hits:
        if not isinstance(h, dict):
            continue
        obj_id = h.get("objectID") or h.get("url") or ""
        if obj_id in seen:
            continue
        seen.add(obj_id)
        out.append(h)
        if len(out) >= limit:
            break
    return out


def fetch_hackernews_stories(
    ticker: str,
    additional_queries: Iterable[str] | None = None,
    days_back: int = 7,
    limit_per_query: int = 8,
    timeout: float = 10.0,
    inter_request_delay: float = 0.3,
) -> str:
    """Fetch recent Hacker News stories mentioning ``ticker`` and return a
    formatted plaintext block.

    ``additional_queries`` adds alternate search strings (e.g. company name)
    so non-ticker discussion is also captured.

    For tickers that are unlikely to have HN signal (e.g. Chinese real-estate
    REITs), the function returns a skip message immediately without making
    HTTP calls.
    """
    queries: list[str] = [ticker.strip()]
    if additional_queries:
        seen_upper = {queries[0].upper()}
        for q in additional_queries:
            q = str(q).strip()
            if not q or q.upper() in seen_upper:
                continue
            seen_upper.add(q.upper())
            queries.append(q)

    # Heuristic skip for non-tech tickers
    if not any(_is_likely_tech_ticker(q) for q in queries):
        return (
            f"<hackernews skipped: HN signal is typically weak for {ticker!r}; "
            "tech / SaaS / semiconductor tickers yield the best results>"
        )

    from_ts = _epoch_seconds(days_back)
    blocks: list[str] = []
    total_stories = 0

    for i, q in enumerate(queries):
        if i > 0:
            time.sleep(inter_request_delay)
        stories = _fetch_hn_items(q, from_ts, limit_per_query, timeout)
        total_stories += len(stories)
        if not stories:
            blocks.append(f"HN search '{q}': <no stories in past {days_back} days>")
            continue

        lines = [f"HN stories for '{q}' — {len(stories)} results:"]
        for s in stories:
            title = (s.get("title") or "").replace("\n", " ").strip()
            url = (s.get("url") or "").strip()
            points = s.get("points", 0)
            comments = s.get("num_comments", 0)
            author = (s.get("author") or "").strip()
            created = s.get("created_at_i")
            created_str = (
                time.strftime("%Y-%m-%d", time.gmtime(created))
                if created else "?"
            )
            hn_url = f"https://news.ycombinator.com/item?id={s.get('objectID')}"
            lines.append(
                f"  [{created_str} · {points:>4}↑ · {comments:>3}c] {title}"
                f"\n    by @{author} — discussion: {hn_url}"
                + (f"\n    link: {url}" if url else "")
            )
        blocks.append("\n".join(lines))

    if total_stories == 0:
        return (
            f"<no Hacker News stories found for search terms {queries!r} "
            f"in the past {days_back} days>"
        )
    return "\n\n".join(blocks)


def fetch_hackernews_feed_items(
    ticker: str,
    *,
    additional_queries: Iterable[str] | None = None,
    days_back: int = 7,
    limit_per_query: int = 8,
    timeout: float = 10.0,
    inter_request_delay: float = 0.3,
) -> list[dict]:
    """Structured HN stories for the API news feed (one dict per story).

    Keys: title, summary, publisher, link, pub_date (ISO or None).
    """
    queries: list[str] = [ticker.strip()]
    if additional_queries:
        seen_upper = {queries[0].upper()}
        for q in additional_queries:
            q = str(q).strip()
            if not q or q.upper() in seen_upper:
                continue
            seen_upper.add(q.upper())
            queries.append(q)

    from_ts = _epoch_seconds(days_back)
    out: list[dict] = []

    for i, q in enumerate(queries):
        if i > 0:
            time.sleep(inter_request_delay)
        stories = _fetch_hn_items(q, from_ts, limit_per_query, timeout)
        for s in stories:
            title = (s.get("title") or "").replace("\n", " ").strip() or "(no title)"
            url = (s.get("url") or "").strip()
            hn_url = f"https://news.ycombinator.com/item?id={s.get('objectID')}"
            created = s.get("created_at_i")
            pub_s = None
            if created is not None:
                try:
                    pub_s = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(created)))
                except (TypeError, ValueError, OSError):
                    pass
            out.append({
                "title": title,
                "summary": f"{s.get('points', 0)} points, {s.get('num_comments', 0)} comments by @{s.get('author') or '?'}",
                "publisher": "news.ycombinator.com",
                "link": url or hn_url,
                "pub_date": pub_s,
            })
    return out
