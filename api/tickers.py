"""Ticker normalization for US and HK equities."""
from __future__ import annotations

import re

# Same regex used by tradingagents.dataflows.utils; inlined here so the API
# module does not pull in pandas just for path validation.
_TICKER_PATH_RE = re.compile(r"^[A-Za-z0-9._\-\^]+$")


def _safe_ticker_component(value: str, *, max_len: int = 32) -> str:
    """Validate ``value`` is safe to interpolate into a filesystem path."""
    if not value or len(value) > max_len:
        raise ValueError(f"Ticker length must be between 1 and {max_len}")
    if not _TICKER_PATH_RE.match(value):
        raise ValueError(
            "Ticker contains invalid characters. "
            "Allowed: letters, digits, dot, dash, underscore, caret."
        )
    return value


def normalize_ticker(ticker: str) -> str:
    """Normalize a ticker symbol for yfinance.

    Rules:
      - US: AAPL, SPY pass through as-is.
      - HK: 0700.HK, 0700hk → normalize to 0700.HK.
      - Reject path-traversal via _safe_ticker_component.
    """
    raw = ticker.strip().upper()

    # Path-safety guard (rejects /, \, .., etc.)
    _safe_ticker_component(raw)

    # Already has .HK suffix
    if raw.endswith(".HK"):
        return raw

    # Ends with HK but missing dot (e.g. 0700HK)
    if raw.endswith("HK") and len(raw) > 2:
        code = raw[:-2]
        if code.isdigit():
            return f"{code}.HK"

    # Pure numeric 4-5 digit HK codes without suffix
    if raw.isdigit() and 4 <= len(raw) <= 5:
        return f"{raw}.HK"

    # US-style tickers pass through
    return raw


def validate_date(date_str: str) -> bool:
    """Validate YYYY-MM-DD format."""
    import datetime

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return False
    try:
        datetime.datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False
