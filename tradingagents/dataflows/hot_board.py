"""Configurable hot-board + prediction-market fetchers with in-memory TTL caching.

Feed shape defaults to a NewsNow-compatible JSON API::

    GET {base_url}/api/s?id={source_id}

Response: JSON array or ``{\"items\": [...]}`` where each item has at least
``title`` and optionally ``url``, ``id``, ``publish_time``.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from tradingagents.dataflows.config import get_config

logger = logging.getLogger(__name__)

_MEMORY: Dict[str, tuple[float, List[Dict[str, Any]]]] = {}


def _now() -> float:
    return time.time()


def _cfg() -> Dict[str, Any]:
    return get_config()


def fetch_hot_board_items(source_id: str, count: int) -> List[Dict[str, Any]]:
    """Pull hot-board headlines from ``hot_news_feed_base_url`` (optional)."""
    cfg = _cfg()
    base = (cfg.get("hot_news_feed_base_url") or "").strip().rstrip("/")
    if not base:
        return []

    ttl = int(cfg.get("hot_news_memory_ttl_sec") or 300)
    timeout = float(cfg.get("hot_news_feed_timeout_sec") or 30)
    cache_key = f"{source_id}_{count}"
    if cache_key in _MEMORY:
        exp, payload = _MEMORY[cache_key]
        if _now() < exp:
            return list(payload)

    url = f"{base}/api/s?id={source_id}"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("hot board fetch failed (%s): %s", url, exc)
        if cache_key in _MEMORY:
            return list(_MEMORY[cache_key][1])
        return []

    items_raw: List[Any]
    if isinstance(data, list):
        items_raw = data
    elif isinstance(data, dict):
        items_raw = data.get("items") or data.get("news") or []
        if not isinstance(items_raw, list):
            items_raw = []
    else:
        items_raw = []

    out: List[Dict[str, Any]] = []
    crawl_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for i, raw in enumerate(items_raw[: max(1, min(count, 100))]):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or raw.get("name") or "").strip()
        if not title:
            continue
        url_s = str(raw.get("url") or raw.get("link") or "").strip() or ""
        pub = raw.get("publish_time") or raw.get("time") or raw.get("date")
        pub_s = str(pub).strip() if pub else ""
        out.append(
            {
                "source_id": source_id,
                "rank": i + 1,
                "title": title,
                "url": url_s,
                "publish_time": pub_s,
                "crawl_time": crawl_time,
                "meta_json": {"raw_keys": list(raw.keys())[:12]},
            }
        )

    _MEMORY[cache_key] = (_now() + ttl, out)
    return out


def format_hot_board_markdown(source_id: str, items: List[Dict[str, Any]]) -> str:
    if not items:
        base = (_cfg().get("hot_news_feed_base_url") or "").strip()
        if not base:
            return (
                "Hot board fetch skipped: `hot_news_feed_base_url` is not set in config. "
                "Set it to a compatible feed base URL (or leave unset to disable)."
            )
        return f"No items parsed for source_id={source_id!r}."

    lines = [f"### Hot board `{source_id}`", ""]
    for it in items:
        title = it.get("title") or ""
        url = it.get("url") or ""
        pub = it.get("publish_time") or ""
        rank = it.get("rank") or ""
        if url:
            lines.append(f"{rank}. [{title}]({url}) — _{pub}_")
        else:
            lines.append(f"{rank}. {title} — _{pub}_")
    return "\n".join(lines)


def fetch_polymarket_markets(limit: int = 15) -> str:
    """Return a compact Markdown snapshot of active Polymarket markets (HTTP, no key)."""
    lim = max(1, min(int(limit or 15), 40))
    url = "https://gamma-api.polymarket.com/markets"
    params = {"active": "true", "closed": "false", "limit": lim}
    try:
        resp = requests.get(url, params=params, timeout=25)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return f"Polymarket request failed: {exc}"

    if not isinstance(data, list):
        return "Polymarket returned an unexpected payload."

    lines: List[str] = ["### Active Polymarket markets (snapshot)", ""]
    for m in data[:lim]:
        if not isinstance(m, dict):
            continue
        q = str(m.get("question") or m.get("title") or "").strip()
        if not q:
            continue
        vol = m.get("volume")
        liq = m.get("liquidity")
        slug = str(m.get("slug") or "").strip()
        extra = []
        if vol is not None:
            extra.append(f"vol={vol}")
        if liq is not None:
            extra.append(f"liq={liq}")
        suffix = f" ({', '.join(extra)})" if extra else ""
        if slug:
            lines.append(f"- **{q}**{suffix} — https://polymarket.com/event/{slug}")
        else:
            lines.append(f"- **{q}**{suffix}")

    if len(lines) <= 2:
        return "No Polymarket markets parsed from response."
    return "\n".join(lines)


def _is_active_polymarket_market(m: dict) -> bool:
    """Return True if a market dict looks open and tradable."""
    if not isinstance(m, dict):
        return False
    # ``closed`` and ``archived`` are more reliable than ``active`` alone.
    if m.get("closed") is True or m.get("archived") is True:
        return False
    return True


def _market_matches_keywords(market: dict, event: dict, keywords: list[str]) -> bool:
    """Check whether a market or its parent event mentions any keyword."""
    text_parts = [
        str(market.get("question") or ""),
        str(market.get("title") or ""),
        str(market.get("description") or ""),
        str(event.get("title") or ""),
        str(event.get("description") or ""),
        str(event.get("ticker") or ""),
        str(event.get("slug") or ""),
    ]
    text = " ".join(text_parts).upper()
    return any(kw in text for kw in keywords)


def _parse_json_field(value: Any) -> Any:
    """Parse a JSON-encoded string (common in Polymarket search responses)."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    return value


def _format_polymarket_market(m: dict) -> str | None:
    """Format a single Polymarket market as a markdown bullet."""
    q = str(m.get("question") or m.get("title") or "").strip()
    if not q:
        return None
    vol = m.get("volume")
    liq = m.get("liquidity")
    slug = str(m.get("slug") or "").strip()
    outcomes = _parse_json_field(m.get("outcomes")) or []
    prices = _parse_json_field(m.get("outcomePrices")) or []
    extra: list[str] = []
    if vol is not None:
        extra.append(f"vol={vol}")
    if liq is not None:
        extra.append(f"liq={liq}")
    # Show outcome probabilities when available
    for o, p in zip(outcomes, prices):
        if o and p is not None:
            try:
                prob = float(p)
                extra.append(f"{o}={prob:.0%}")
            except (TypeError, ValueError):
                extra.append(f"{o}={p}")
    suffix = f" ({', '.join(extra)})" if extra else ""
    if slug:
        return f"- **{q}**{suffix} — https://polymarket.com/event/{slug}"
    return f"- **{q}**{suffix}"


def fetch_polymarket_for_ticker(
    ticker: str,
    additional_queries: list[str] | None = None,
    limit: int = 15,
) -> str:
    """Return Polymarket markets relevant to a specific ticker or company.

    Uses Polymarket's full-text ``/public-search`` endpoint (no API key),
    which is far more precise than fetching a small snapshot of all markets
    and filtering client-side.
    """
    keywords = [ticker.strip().upper()]
    if additional_queries:
        for q in additional_queries:
            q = str(q).strip().upper()
            if q and q not in keywords:
                keywords.append(q)

    lim = max(1, min(int(limit or 15), 100))
    url = "https://gamma-api.polymarket.com/public-search"

    seen: set[str] = set()
    matches: list[dict] = []
    for kw in keywords:
        if len(matches) >= limit:
            break
        params = {"q": kw, "limit": lim}
        try:
            resp = requests.get(url, params=params, timeout=25)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            return f"Polymarket request failed: {exc}"

        if not isinstance(data, dict):
            return "Polymarket returned an unexpected payload."

        events = data.get("events") or []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            for m in ev.get("markets") or []:
                if not _is_active_polymarket_market(m):
                    continue
                mid = str(m.get("id") or m.get("slug") or "")
                if not mid or mid in seen:
                    continue
                if not _market_matches_keywords(m, ev, keywords):
                    continue
                seen.add(mid)
                matches.append(m)
                if len(matches) >= limit:
                    break
            if len(matches) >= limit:
                break

    if not matches:
        return (
            f"<no active Polymarket markets matched keywords {keywords!r}>"
        )

    lines: List[str] = [f"### Polymarket markets related to {ticker}", ""]
    for m in matches:
        formatted = _format_polymarket_market(m)
        if formatted:
            lines.append(formatted)

    return "\n".join(lines)


def normalize_hot_board_rows(source_id: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach defaults for repository upsert."""
    rows: List[Dict[str, Any]] = []
    for it in items:
        rows.append(
            {
                "source_id": source_id,
                "rank": int(it.get("rank") or 0),
                "title": str(it.get("title") or ""),
                "url": str(it.get("url") or ""),
                "content": it.get("content"),
                "publish_time": str(it.get("publish_time") or ""),
                "crawl_time": str(it.get("crawl_time") or ""),
                "sentiment_score": it.get("sentiment_score"),
                "analysis_note": it.get("analysis_note"),
                "meta_json": it.get("meta_json") if isinstance(it.get("meta_json"), dict) else {},
            }
        )
    return rows
