"""StockTwits public symbol-stream fetcher.

StockTwits exposes a per-symbol message stream at
``api.stocktwits.com/api/2/streams/symbol/{ticker}.json`` that requires no
API key, no OAuth, and no registration. Each message includes a
user-labeled sentiment field (``Bullish``/``Bearish``/null), the message
body, timestamp, and posting user.

The function is deliberately self-contained: short timeout, graceful
degradation on any HTTP or parse failure, and a string return type so
the calling agent gets a uniform interface regardless of whether the
network call succeeded.
"""

from __future__ import annotations

import http.client
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_API = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"

# Per-symbol streams are US-retail-centric; yfinance-style intl suffixes almost always 404.
_STOCKTWITS_UNSUPPORTED_SUFFIXES = frozenset({
    "HK", "L", "TO", "V", "AX", "DE", "PA", "AS", "MI", "SW", "ST", "OL", "CO", "IS",
    "SS", "SZ", "NS", "BO", "SA", "JK", "KL", "T", "TW", "SI", "NZ", "LS", "MC", "BR", "MX",
})


def stocktwits_stream_likely_available(ticker: str) -> bool:
    """False when StockTwits typically has no stream for this symbol (skip HTTP)."""
    t = (ticker or "").strip().upper()
    if "." not in t:
        return True
    suf = t.rsplit(".", 1)[-1]
    return suf not in _STOCKTWITS_UNSUPPORTED_SUFFIXES


def _http_status(exc: BaseException) -> Optional[int]:
    return getattr(exc, "status", None) or getattr(exc, "code", None)


def fetch_stocktwits_messages(ticker: str, limit: int = 30, timeout: float = 10.0) -> str:
    """Fetch recent StockTwits messages for ``ticker`` and return them as a
    formatted plaintext block ready for prompt injection.

    Returns a placeholder string when the endpoint is unreachable, the
    symbol has no messages, or the response shape is unexpected — the
    caller never has to special-case None or exceptions.
    """
    sym = (ticker or "").strip().upper() or "UNKNOWN"
    if not stocktwits_stream_likely_available(sym):
        return (
            "<stocktwits skipped: StockTwits has no reliable stream for this exchange suffix "
            f"({sym}); US-listed symbols work best — rely on Yahoo news and Reddit for this ticker>"
        )
    url = _API.format(ticker=sym)
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except HTTPError as exc:
        st = _http_status(exc)
        if st == 404:
            logger.info("StockTwits: symbol not found (404) for %s", ticker)
            return (
                "<stocktwits: symbol not on StockTwits (404). Many non-US tickers are unsupported; "
                "use other sources in this prompt>"
            )
        logger.warning("StockTwits fetch failed for %s: %s", ticker, exc)
        return f"<stocktwits unavailable: HTTP {st or type(exc).__name__}>"
    except (URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("StockTwits fetch failed for %s: %s", ticker, exc)
        return f"<stocktwits unavailable: {type(exc).__name__}>"
    except http.client.HTTPException as exc:
        logger.warning("StockTwits transport error for %s: %s", ticker, exc)
        return f"<stocktwits unavailable: transport error>"

    messages = data.get("messages", []) if isinstance(data, dict) else []
    if not messages:
        return f"<no StockTwits messages found for ${sym}>"

    lines = []
    bullish = bearish = unlabeled = 0
    for m in messages[:limit]:
        created = m.get("created_at", "")
        user = (m.get("user") or {}).get("username", "?")
        entities = m.get("entities") or {}
        sentiment_obj = entities.get("sentiment") or {}
        sentiment = sentiment_obj.get("basic") if isinstance(sentiment_obj, dict) else None
        body = (m.get("body") or "").replace("\n", " ").strip()
        if len(body) > 280:
            body = body[:280] + "…"

        if sentiment == "Bullish":
            bullish += 1
            tag = "Bullish"
        elif sentiment == "Bearish":
            bearish += 1
            tag = "Bearish"
        else:
            unlabeled += 1
            tag = "no-label"
        lines.append(f"[{created} · @{user} · {tag}] {body}")

    total = bullish + bearish + unlabeled
    bull_pct = round(100 * bullish / total) if total else 0
    bear_pct = round(100 * bearish / total) if total else 0
    summary = (
        f"Bullish: {bullish} ({bull_pct}%) · "
        f"Bearish: {bearish} ({bear_pct}%) · "
        f"Unlabeled: {unlabeled} · "
        f"Total: {total} most-recent messages"
    )
    return summary + "\n\n" + "\n".join(lines)


def fetch_stocktwits_feed_items(
    ticker: str,
    *,
    limit: int = 30,
    timeout: float = 10.0,
) -> list[dict]:
    """Structured messages for the API news feed.

    Each dict: title, summary, publisher, link, pub_date (ISO or ""),
    sentiment_basic (``Bullish`` / ``Bearish`` / None).

    Returns an empty list when the symbol is unsupported or StockTwits returns 404 —
    callers should not treat that as a hard failure.
    """
    sym = (ticker or "").strip().upper() or "UNKNOWN"
    if not stocktwits_stream_likely_available(sym):
        logger.info("StockTwits feed skipped for %s (exchange not supported on StockTwits)", sym)
        return []
    url = _API.format(ticker=sym)
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except HTTPError as exc:
        st = _http_status(exc)
        if st == 404:
            logger.info("StockTwits structured fetch: symbol not found (404) for %s", sym)
            return []
        logger.warning("StockTwits structured fetch failed for %s: %s", ticker, exc)
        raise
    except (URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("StockTwits structured fetch failed for %s: %s", ticker, exc)
        raise

    messages = data.get("messages", []) if isinstance(data, dict) else []
    out: list[dict] = []
    for m in messages[:limit]:
        body = (m.get("body") or "").replace("\n", " ").strip()
        if not body:
            continue
        title = body if len(body) <= 140 else body[:137] + "…"
        user = (m.get("user") or {}).get("username") or ""
        mid = m.get("id")
        link = (
            f"https://stocktwits.com/{user}/message/{mid}"
            if user and mid is not None
            else f"https://stocktwits.com/symbol/{ticker.upper()}"
        )
        created = m.get("created_at") or ""
        pub_s = ""
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                pub_s = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except (ValueError, TypeError):
                pub_s = str(created)
        entities = m.get("entities") or {}
        sentiment_obj = entities.get("sentiment") or {}
        basic = sentiment_obj.get("basic") if isinstance(sentiment_obj, dict) else None
        out.append({
            "title": title,
            "summary": body,
            "publisher": f"@{user}" if user else "StockTwits",
            "link": link,
            "pub_date": pub_s or None,
            "sentiment_basic": basic,
        })
    return out
