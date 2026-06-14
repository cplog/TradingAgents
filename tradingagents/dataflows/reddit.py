"""Reddit search fetcher for ticker-specific discussion posts.

Reddit's public JSON endpoints (``reddit.com/r/{sub}/search.json``) are
aggressively blocked for non-browser clients from many networks.  When JSON
fails, we fall back to Reddit's public Atom/RSS search feed
(``search.rss``), which remains readable with a realistic user-agent and
rate-limit discipline.

Returns formatted plaintext blocks ready for prompt injection. Degrades
gracefully — returns a placeholder string rather than raising, so callers
never have to special-case missing data.
"""

from __future__ import annotations

import html
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_JSON_API = "https://www.reddit.com/r/{sub}/search.json?{qs}"
_RSS_API = "https://www.reddit.com/r/{sub}/search.rss?{qs}"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

# Default subreddits ordered roughly by signal density for ticker-specific
# discussion. wallstreetbets has the most volume but most noise; stocks /
# investing trend more measured. Caller can override.
DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


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


def _strip_html(raw: str | None) -> str:
    """Remove HTML tags and collapse whitespace."""
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_iso_to_utc_timestamp(value: str | None) -> float | None:
    """Parse an ISO-8601 string (with trailing Z) to a UTC epoch timestamp."""
    if not value:
        return None
    try:
        s = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError, OSError):
        return None


def _parse_rss_entry(entry: ET.Element) -> dict:
    """Turn a Reddit Atom ``<entry>`` into a dict compatible with JSON posts."""
    title = (entry.find("atom:title", _ATOM_NS).text or "").strip()
    content_html = ""
    content_el = entry.find("atom:content", _ATOM_NS)
    if content_el is not None and content_el.text:
        content_html = content_el.text

    # Prefer the dedicated link; fall back to the first <a> in content.
    permalink = ""
    link_el = entry.find("atom:link", _ATOM_NS)
    if link_el is not None:
        permalink = (link_el.get("href") or "").strip()
    if not permalink:
        match = re.search(r'href="([^"]+)"', content_html)
        if match:
            permalink = html.unescape(match.group(1))

    updated_el = entry.find("atom:updated", _ATOM_NS)
    published_el = entry.find("atom:published", _ATOM_NS)
    date_str = ""
    if published_el is not None and published_el.text:
        date_str = published_el.text
    elif updated_el is not None and updated_el.text:
        date_str = updated_el.text

    created_utc = _parse_iso_to_utc_timestamp(date_str)

    # The RSS feed intentionally omits score/comment counts for search results.
    return {
        "id": permalink,
        "title": title,
        "selftext": _strip_html(content_html),
        "permalink": permalink,
        "url": permalink,
        "created_utc": created_utc,
        "score": None,
        "num_comments": None,
    }


def _fetch_subreddit_rss(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
) -> list[dict]:
    """Fetch Reddit search results via the public Atom/RSS feed."""
    qs = urlencode({
        "q": ticker,
        "restrict_sr": "on",
        "sort": "new",
        "t": "week",
        "limit": limit,
    })
    url = _RSS_API.format(sub=sub, qs=qs)
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/atom+xml"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as exc:
        logger.warning("Reddit RSS fetch failed for r/%s · %s: %s", sub, ticker, exc)
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        logger.warning("Reddit RSS parse failed for r/%s · %s: %s", sub, ticker, exc)
        return []

    entries = root.findall(".//atom:entry", _ATOM_NS)
    posts: list[dict] = []
    for entry in entries[:limit]:
        if not isinstance(entry, ET.Element):
            continue
        try:
            posts.append(_parse_rss_entry(entry))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Reddit RSS entry parse failed for r/%s: %s", sub, exc)
    return posts


def _fetch_subreddit_json(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
) -> list[dict]:
    """Fetch Reddit search results via the JSON endpoint."""
    qs = urlencode({
        "q": ticker,
        "restrict_sr": "on",
        "sort": "new",
        "t": "week",  # last 7 days
        "limit": limit,
    })
    url = _JSON_API.format(sub=sub, qs=qs)
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("Reddit JSON fetch failed for r/%s · %s: %s", sub, ticker, exc)
        return []
    children = (payload.get("data") or {}).get("children") or []
    return [c.get("data", {}) for c in children if isinstance(c, dict)]


def _fetch_subreddit(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
) -> list[dict]:
    """Fetch posts for one subreddit, falling back from JSON to RSS."""
    posts = _fetch_subreddit_json(ticker, sub, limit, timeout)
    if posts:
        return posts
    logger.info("Reddit JSON returned no data for r/%s · %s; trying RSS fallback", sub, ticker)
    return _fetch_subreddit_rss(ticker, sub, limit, timeout)


def fetch_reddit_posts(
    ticker: str,
    subreddits: Iterable[str] = DEFAULT_SUBREDDITS,
    limit_per_sub: int = 5,
    timeout: float = 10.0,
    inter_request_delay: float = 1.5,
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
            score = p.get("score")
            comments = p.get("num_comments")
            created = p.get("created_utc")
            created_str = (
                time.strftime("%Y-%m-%d", time.gmtime(created)) if created else "?"
            )
            selftext = (p.get("selftext") or "").replace("\n", " ").strip()
            if len(selftext) > 240:
                selftext = selftext[:240] + "…"
            score_part = f"{score:>4}↑" if score is not None else "  ?↑"
            comments_part = f"{comments:>3}c" if comments is not None else " ?c"
            lines.append(
                f"  [{created_str} · {score_part} · {comments_part}] {title}"
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
    inter_request_delay: float = 1.5,
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
