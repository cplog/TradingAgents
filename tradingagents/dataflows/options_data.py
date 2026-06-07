"""yfinance options chain fetcher for the options strategist.

No API key required. Uses the same indirection pattern as api.dimensions.facts
so tests can monkeypatch _yf_ticker.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from api.dimensions.facts import _yf_ticker

logger = logging.getLogger(__name__)


def _clean_option_row(row: Any) -> Optional[Dict[str, Any]]:
    """Normalize a single option chain row to a JSON-safe dict."""
    if row is None:
        return None
    try:
        return {
            "strike": float(row.get("strike", 0)) if row.get("strike") is not None else None,
            "lastPrice": float(row.get("lastPrice", 0)) if row.get("lastPrice") is not None else None,
            "bid": float(row.get("bid", 0)) if row.get("bid") is not None else None,
            "ask": float(row.get("ask", 0)) if row.get("ask") is not None else None,
            "impliedVolatility": float(row.get("impliedVolatility", 0))
            if row.get("impliedVolatility") is not None
            else None,
            "volume": int(row.get("volume", 0)) if row.get("volume") is not None else None,
            "openInterest": int(row.get("openInterest", 0))
            if row.get("openInterest") is not None
            else None,
        }
    except (TypeError, ValueError):
        return None


def get_options_expirations(ticker: str) -> List[str]:
    """Return available expiration dates for ``ticker`` (YYYY-MM-DD strings).

    Returns empty list on failure so the caller can degrade gracefully.
    """
    try:
        tk = _yf_ticker(ticker)
        opts = tk.options
        if opts is None:
            return []
        return list(opts)
    except Exception as exc:
        logger.warning("yfinance options expirations failed for %s: %s", ticker, exc)
        return []


def get_options_context(ticker: str) -> Dict[str, Any]:
    """Fetch non-chain options-relevant context: earnings calendar, short interest, dividends.

    Returns a dict with optional keys: ``earnings_date``, ``ex_dividend_date``,
    ``short_percent_float``, ``short_ratio``, ``error``.
    """
    out: Dict[str, Any] = {}
    try:
        tk = _yf_ticker(ticker)
        info = tk.info or {}
        cal = tk.calendar
        if cal is not None:
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if ed is not None:
                    if isinstance(ed, (list, tuple)) and len(ed) > 0:
                        out["earnings_date"] = str(ed[0])
                    else:
                        out["earnings_date"] = str(ed)
                ex_div = cal.get("Ex-Dividend Date")
                if ex_div is not None:
                    out["ex_dividend_date"] = str(ex_div)
        spf = info.get("shortPercentOfFloat")
        if spf is not None:
            try:
                out["short_percent_float"] = float(spf)
            except (TypeError, ValueError):
                pass
        sr = info.get("shortRatio")
        if sr is not None:
            try:
                out["short_ratio"] = float(sr)
            except (TypeError, ValueError):
                pass
    except Exception as exc:
        logger.warning("yfinance options context failed for %s: %s", ticker, exc)
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def get_options_chain(ticker: str, expiration: str) -> Dict[str, Any]:
    """Return cleaned option chain for ``ticker`` at ``expiration``.

    Returns a dict with ``expiration``, ``fetched_at``, ``underlying_price``,
    ``calls``, ``puts``, and optionally ``error``.  On total failure every
    value except ``error`` may be absent/None.
    """
    out: Dict[str, Any] = {
        "ticker": ticker,
        "expiration": expiration,
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "underlying_price": None,
        "calls": [],
        "puts": [],
    }
    try:
        tk = _yf_ticker(ticker)
        info = tk.info or {}
        raw_price = info.get("regularMarketPrice")
        if raw_price is None:
            raw_price = info.get("currentPrice")
        if raw_price is not None:
            out["underlying_price"] = float(raw_price)

        chain = tk.option_chain(expiration)
        if chain is None:
            out["error"] = "yfinance returned empty option chain"
            return out

        calls_df = getattr(chain, "calls", None)
        puts_df = getattr(chain, "puts", None)

        if calls_df is not None and not getattr(calls_df, "empty", True):
            out["calls"] = [
                r for r in (_clean_option_row(row) for _, row in calls_df.iterrows()) if r
            ]
        if puts_df is not None and not getattr(puts_df, "empty", True):
            out["puts"] = [
                r for r in (_clean_option_row(row) for _, row in puts_df.iterrows()) if r
            ]
    except Exception as exc:
        logger.warning("yfinance option chain failed for %s %s: %s", ticker, expiration, exc)
        out["error"] = f"{type(exc).__name__}: {exc}"

    return out
