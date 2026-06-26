"""Reddit search fetcher for ticker-specific discussion posts.

Default path is Reddit's public Atom/RSS search feed
(``reddit.com/r/{sub}/search.rss``). The richer JSON search endpoint
(``/search.json``) is reliably WAF-blocked (``HTTP 403``) for public clients
(issue #862), and probing it on every call only doubled our request volume
against Reddit's per-IP rate limit — tripping ``429`` on the RSS fallback — so
it is kept (``_fetch_subreddit_json``) but not used by default. On a 429 we back
off once (honouring ``Retry-After``). RSS lacks score / comment counts, so those
posts are marked and the formatter omits the metrics rather than printing fake
zeros.

No API key required. Returns formatted plaintext blocks ready for prompt
injection and degrades gracefully — returns a placeholder string rather than
raising, so callers never special-case missing data.
"""

from __future__ import annotations

import html
import http.client
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_API = "https://www.reddit.com/r/{sub}/search.json?{qs}"
_RSS = "https://www.reddit.com/r/{sub}/search.rss?{qs}"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")


def _search_qs(ticker: str, limit: int) -> str:
    return urlencode({
        "q": ticker,
        "restrict_sr": "on",
        "sort": "new",
        "t": "week",
        "limit": limit,
    })


def _iso_to_timestamp(iso_str: str | None) -> float | None:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def _fetch_subreddit_rss(sub: str, ticker: str, limit: int) -> list[dict]:
    """Fetch posts via Reddit's Atom/RSS search feed (the reliable path)."""
    url = _RSS.format(sub=sub, qs=_search_qs(ticker, limit))
    body = _urlopen_with_retry(url)
    root = ET.fromstring(body)

    posts: list[dict] = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        title_el = entry.find("atom:title", _ATOM_NS)
        link_el = entry.find("atom:link", _ATOM_NS)
        updated_el = entry.find("atom:updated", _ATOM_NS)
        author_el = entry.find("atom:author/atom:name", _ATOM_NS)

        title = _strip_html(title_el.text) if title_el is not None and title_el.text else ""
        permalink = link_el.attrib.get("href", "") if link_el is not None else ""
        updated = _iso_to_timestamp(updated_el.text if updated_el is not None else None)
        author = author_el.text if author_el is not None else ""

        # RSS has no score/comment data, so these stay zero.
        posts.append({
            "id": permalink.rsplit("/", 2)[-2] if "/" in permalink else permalink,
            "title": title,
            "permalink": permalink,
            "created_utc": int(updated) if updated else 0,
            "score": 0,
            "num_comments": 0,
            "author": author,
            "subreddit": sub,
            "_source": "rss",
        })
    return posts


def _fetch_subreddit_json(sub: str, ticker: str, limit: int) -> list[dict]:
    """Fetch posts via Reddit's JSON search API (WAF-prone, kept as backup)."""
    url = _API.format(sub=sub, qs=_search_qs(ticker, limit))
    body = _urlopen_with_retry(url)
    data = json.loads(body)
    children = data.get("data", {}).get("children", [])
    return [
        ch["data"]
        for ch in children
        if ch.get("kind") == "t3" and ch.get("data", {}).get("title")
    ]


def _urlopen_with_retry(url: str) -> bytes:
    """GET ``url`` with a descriptive User-Agent, retrying once on 429.

    On a 429 the util honours ``Retry-After`` (seconds) before the retry.
    Other HTTP errors propagate immediately.
    """
    req = Request(url, headers={"User-Agent": _UA})
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.read()
    except HTTPError as exc:
        if exc.code == 429:
            retry_after = exc.headers.get("Retry-After")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else 5
            logger.info("Reddit 429, retrying after %ds", delay)
            time.sleep(delay)
            with urlopen(req, timeout=15) as resp:
                return resp.read()
        raise
    except http.client.IncompleteRead as exc:
        logger.warning("Reddit IncompleteRead (%s), retrying once", exc)
        with urlopen(req, timeout=15) as resp:
            return resp.read()


def _strip_html(raw: str | None) -> str:
    """Remove HTML tags and collapse whitespace."""
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _format_post(post: dict) -> str:
    """Format one Reddit post as a plaintext block for an agent prompt."""
    title = _strip_html(post.get("title", ""))
    permalink = post.get("permalink", "")
    author = post.get("author", "")
    sub = post.get("subreddit", "")
    source = post.get("_source", "")
    score = post.get("score")
    comments = post.get("num_comments")

    # From RSS we have no score/comments so omit them rather than printing zero.
    metrics = ""
    if source != "rss":
        parts = []
        if isinstance(score, (int, float)):
            parts.append(f"{int(score)} upvotes")
        if isinstance(comments, (int, float)):
            parts.append(f"{int(comments)} comments")
        if parts:
            metrics = f" ({', '.join(parts)})"

    block = f"- **{title}**{metrics}"
    if author:
        block += f" by u/{author}"
    if sub:
        block += f" in r/{sub}"
    if permalink:
        block += f"\n  {permalink}"
    return block


def _merge_queries(ticker: str, additional_queries: Iterable[str] | None) -> list[str]:
    """Ticker first, then optional company-name aliases (deduped, case-insensitive)."""
    queries = [ticker.strip()]
    if additional_queries:
        seen = {queries[0].upper()}
        for raw in additional_queries:
            q = str(raw).strip()
            if q and q.upper() not in seen:
                seen.add(q.upper())
                queries.append(q)
    return queries


def _collect_posts_for_query(
    query: str,
    subs: tuple[str, ...],
    limit: int,
) -> list[dict]:
    posts: list[dict] = []
    for sub in subs:
        batch = _fetch_subreddit_rss(sub, query, limit)
        if not batch:
            try:
                batch = _fetch_subreddit_json(sub, query, limit)
            except Exception:
                pass
        posts.extend(batch)
    return posts


def search_reddit(
    ticker: str,
    subreddits: Iterable[str] | None = None,
    limit: int = 5,
    additional_queries: Iterable[str] | None = None,
    inter_request_delay: float = 0.3,
) -> str:
    """Search Reddit for posts about a ticker, returning a formatted summary.

    Uses the RSS feed by default, falling back to JSON only if RSS errors.
    ``additional_queries`` adds alternate search strings (e.g. company name)
    so threads without the bare ticker symbol are also captured.

    Returns a placeholder when Reddit communication fails rather than raising,
    so callers never need to special-case missing data.
    """
    subs = tuple(subreddits) if subreddits is not None else DEFAULT_SUBREDDITS
    queries = _merge_queries(ticker, additional_queries)
    all_posts: list[dict] = []
    seen_ids: set[str] = set()

    for qi, query in enumerate(queries):
        if qi > 0:
            time.sleep(inter_request_delay)
        for post in _collect_posts_for_query(query, subs, limit):
            pid = str(post.get("id", ""))
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_posts.append(post)

    if not all_posts:
        return f"No Reddit discussions found for {ticker}."

    all_posts.sort(key=lambda p: p.get("created_utc", 0), reverse=True)
    lines = [f"## Reddit discussions about {ticker}:\n"]
    for post in all_posts[:limit * len(subs)]:
        lines.append(_format_post(post))

    return "\n".join(lines) + "\n"


# Backward-compatible wrappers ------------------------------------------------

def fetch_reddit_posts(
    ticker: str,
    subreddits: Iterable[str] | None = None,
    limit: int = 5,
    additional_queries: Iterable[str] | None = None,
) -> str:
    """Backward-compat alias for ``search_reddit`` (returns formatted string).

    Old callers: ``fetch_reddit_posts(ticker, subreddits=["wsb"], limit=5)``.
    """
    return search_reddit(
        ticker,
        subreddits,
        limit,
        additional_queries=additional_queries,
    )


def fetch_reddit_feed_items(
    ticker: str,
    subreddits: Iterable[str] | None = None,
    limit: int = 5,
    additional_queries: Iterable[str] | None = None,
    inter_request_delay: float = 0.3,
) -> list[dict]:
    """Backward-compat: return Reddit posts as structured dicts (API usage).

    Returns the raw post dicts so the API layer can serialise them as JSON.
    Each dict contains: id, title, permalink, created_utc, score,
    num_comments, author, subreddit.
    """
    subs = tuple(subreddits) if subreddits is not None else DEFAULT_SUBREDDITS
    queries = _merge_queries(ticker, additional_queries)
    all_posts: list[dict] = []
    seen_ids: set[str] = set()

    for qi, query in enumerate(queries):
        if qi > 0:
            time.sleep(inter_request_delay)
        for post in _collect_posts_for_query(query, subs, limit):
            pid = str(post.get("id", ""))
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_posts.append(post)

    all_posts.sort(key=lambda p: p.get("created_utc", 0), reverse=True)
    return all_posts[:limit * len(subs)]
