"""Tavily web search client with typed exceptions."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class TavilyError(Exception):
    """Base Tavily API error."""


class TavilyAuthError(TavilyError):
    """Missing or invalid API key."""


class TavilyRateLimitError(TavilyError):
    """Rate limit or quota exceeded."""


class TavilyRequestError(TavilyError):
    """Non-recoverable HTTP or payload error."""


def get_tavily_api_key() -> str:
    key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not key:
        raise TavilyAuthError("TAVILY_API_KEY is not set")
    return key


def get_tavily_daily_cap() -> int:
    raw = (os.getenv("TAVILY_DAILY_CAP") or "100").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 100


def search(
    query: str,
    *,
    max_results: int = 10,
    search_depth: str = "basic",
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Run a Tavily search and return normalized article dicts."""
    key = api_key or get_tavily_api_key()
    payload = {
        "api_key": key,
        "query": query.strip(),
        "max_results": max(1, min(max_results, 20)),
        "search_depth": search_depth,
        "include_answer": False,
        "include_raw_content": False,
    }
    try:
        resp = requests.post(TAVILY_SEARCH_URL, json=payload, timeout=45)
    except requests.RequestException as exc:
        raise TavilyRequestError(f"Tavily request failed: {exc}") from exc

    if resp.status_code == 401:
        raise TavilyAuthError("Tavily API key rejected (401)")
    if resp.status_code == 429:
        raise TavilyRateLimitError("Tavily rate limit (429)")
    if resp.status_code >= 400:
        raise TavilyRequestError(f"Tavily HTTP {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise TavilyRequestError("Tavily returned non-JSON body") from exc

    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return []

    out: List[Dict[str, Any]] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "title": str(row.get("title") or "").strip(),
                "url": str(row.get("url") or "").strip(),
                "snippet": str(row.get("content") or row.get("snippet") or "").strip() or None,
                "published_at": row.get("published_date") or row.get("published_at"),
                "source": row.get("source") or "tavily",
            }
        )
    return [r for r in out if r.get("title") and r.get("url")]
