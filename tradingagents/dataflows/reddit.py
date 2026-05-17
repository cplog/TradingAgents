"""Reddit search fetcher for ticker-specific discussion posts.

Uses Reddit's public JSON endpoints (``reddit.com/r/{sub}/search.json``)
which do not require an API key. Public throughput is ~10 requests per
minute per IP, well within budget for a single agent run that queries
a handful of finance subreddits per ticker.

Returns formatted plaintext blocks ready for prompt injection. Degrades
gracefully — returns a placeholder string rather than raising, so callers
never have to special-case missing data.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_API = "https://www.reddit.com/r/{sub}/search.json?{qs}"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"

# Default subreddits ordered roughly by signal density for ticker-specific
# discussion. wallstreetbets has the most volume but most noise; stocks /
# investing trend more measured. Caller can override.
DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")


def _dedupe_reddit_posts(posts: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for p in posts:
        pid = p.get("id") or p.get("permalink") or ""
        pid = str(pid)
        if pid in seen:
            continue
        seen.add(pid)
        out.append(p)
    return out


def _fetch_subreddit(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
) -> list[dict]:
    qs = urlencode({
        "q": ticker,
        "restrict_sr": "on",
        "sort": "new",
        "t": "week",  # last 7 days
        "limit": limit,
    })
    url = _API.format(sub=sub, qs=qs)
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("Reddit fetch failed for r/%s · %s: %s", sub, ticker, exc)
        return []
    children = (payload.get("data") or {}).get("children") or []
    return [c.get("data", {}) for c in children if isinstance(c, dict)]


def fetch_reddit_posts(
    ticker: str,
    subreddits: Iterable[str] = DEFAULT_SUBREDDITS,
    limit_per_sub: int = 5,
    timeout: float = 10.0,
    inter_request_delay: float = 0.4,
    additional_queries: Iterable[str] | None = None,
) -> str:
    """Fetch recent Reddit posts mentioning ``ticker`` across finance
    subreddits and return them as a formatted plaintext block.

    ``additional_queries`` adds alternate search strings (e.g. company name from
    yfinance) so non-US tickers (``6060.HK``) can still match discussion that
    omits the exchange-qualified symbol.

    ``inter_request_delay`` keeps us under Reddit's public rate limit
    (~10 req/min per IP) even if the caller queries many subreddits.
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

    blocks = []
    total_posts = 0
    for i, sub in enumerate(subreddits):
        if i > 0:
            time.sleep(inter_request_delay)
        collected: list[dict] = []
        inner_first = True
        for q in queries:
            if not inner_first:
                time.sleep(inter_request_delay)
            inner_first = False
            posts = _fetch_subreddit(q, sub, limit_per_sub, timeout)
            collected.extend(posts)
            collected = _dedupe_reddit_posts(collected)
            if len(collected) >= limit_per_sub:
                collected = collected[:limit_per_sub]
                break
        posts = collected
        total_posts += len(posts)
        if not posts:
            blocks.append(
                f"r/{sub}: <no posts found mentioning any of {queries!r} in the past 7 days>"
            )
            continue

        qstr = ", ".join(queries)
        lines = [f"r/{sub} — {len(posts)} recent posts (search terms: {qstr}):"]
        for p in posts:
            title = (p.get("title") or "").replace("\n", " ").strip()
            score = p.get("score", 0)
            comments = p.get("num_comments", 0)
            created = p.get("created_utc")
            created_str = (
                time.strftime("%Y-%m-%d", time.gmtime(created)) if created else "?"
            )
            selftext = (p.get("selftext") or "").replace("\n", " ").strip()
            if len(selftext) > 240:
                selftext = selftext[:240] + "…"
            lines.append(
                f"  [{created_str} · {score:>4}↑ · {comments:>3}c] {title}"
                + (f"\n    body excerpt: {selftext}" if selftext else "")
            )
        blocks.append("\n".join(lines))

    if total_posts == 0:
        return (
            f"<no Reddit posts found for search terms {queries!r} across "
            f"{', '.join(f'r/{s}' for s in subreddits)} in the past 7 days>"
        )
    return "\n\n".join(blocks)


def _reddit_post_permalink(p: dict) -> str:
    """Best URL for opening a post (self or link)."""
    url = (p.get("url") or "").strip()
    if url.startswith("http") and "reddit.com" not in url:
        return url
    perm = (p.get("permalink") or "").strip()
    if perm.startswith("/"):
        return f"https://www.reddit.com{perm}"
    if url.startswith("http"):
        return url
    return ""


def fetch_reddit_feed_items(
    ticker: str,
    *,
    subreddits: Iterable[str] = DEFAULT_SUBREDDITS,
    limit_per_sub: int = 5,
    timeout: float = 10.0,
    inter_request_delay: float = 0.4,
    additional_queries: Iterable[str] | None = None,
) -> list[dict]:
    """Structured posts for the API news feed (one dict per post).

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

    out: list[dict] = []
    for i, sub in enumerate(subreddits):
        if i > 0:
            time.sleep(inter_request_delay)
        collected: list[dict] = []
        inner_first = True
        for q in queries:
            if not inner_first:
                time.sleep(inter_request_delay)
            inner_first = False
            posts = _fetch_subreddit(q, sub, limit_per_sub, timeout)
            collected.extend(posts)
            collected = _dedupe_reddit_posts(collected)
            if len(collected) >= limit_per_sub:
                collected = collected[:limit_per_sub]
                break
        for p in collected:
            title = (p.get("title") or "").replace("\n", " ").strip() or "(no title)"
            selftext = (p.get("selftext") or "").replace("\n", " ").strip()
            if len(selftext) > 500:
                selftext = selftext[:500] + "…"
            created = p.get("created_utc")
            pub_s = None
            if created is not None:
                try:
                    pub_s = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(created)))
                except (TypeError, ValueError, OSError):
                    pass
            out.append({
                "title": title,
                "summary": selftext,
                "publisher": f"r/{sub}",
                "link": _reddit_post_permalink(p),
                "pub_date": pub_s,
            })
    return out
