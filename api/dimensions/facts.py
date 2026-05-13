"""Deterministic yfinance fact extraction for the dimensions layer.

No LLM. Single yfinance Ticker call per stock. Missing fields are stored
as None and recorded in `data_quality_flags`.
"""
from __future__ import annotations

import logging
import math
from typing import Any, List, Optional, Tuple

from api.dimensions.schemas import FactSnapshot

logger = logging.getLogger(__name__)


class FactExtractionError(RuntimeError):
    """Raised when yfinance is unreachable or returns malformed payload."""


# Indirection so tests can monkeypatch.
def _yf_ticker(ticker: str):
    import yfinance as yf
    return yf.Ticker(ticker)


def _maybe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _maybe_int(v: Any) -> Optional[int]:
    f = _maybe_float(v)
    return int(f) if f is not None else None


_FIELD_TO_INFO_KEY = {
    "currency": "currency",
    "exchange": "exchange",
    "sector": "sector",
    "industry": "industry",
    "market_cap_usd": "marketCap",
    "price": "regularMarketPrice",
    "price_52w_high": "fiftyTwoWeekHigh",
    "beta": "beta",
    "pe_ttm": "trailingPE",
    "forward_pe": "forwardPE",
    "peg": "pegRatio",
    "ev_ebitda": "enterpriseToEbitda",
    "ps_ttm": "priceToSalesTrailing12Months",
    "pb": "priceToBook",
    "revenue_growth_yoy": "revenueGrowth",
    "eps_growth_yoy": "earningsGrowth",
    "roe": "returnOnEquity",
    "gross_margin": "grossMargins",
    "operating_margin": "operatingMargins",
    "net_margin": "profitMargins",
    "debt_to_equity": "debtToEquity",
    "current_ratio": "currentRatio",
    "dividend_yield": "dividendYield",
    "payout_ratio": "payoutRatio",
    "analyst_target_mean": "targetMeanPrice",
    "analyst_recommendation_mean": "recommendationMean",
}

_INT_FIELDS = {"analyst_count"}


def extract_facts(ticker: str, as_of_date: str) -> Tuple[FactSnapshot, List[str]]:
    """Return (FactSnapshot, data_quality_flags). Raises FactExtractionError on yfinance error."""
    try:
        tk = _yf_ticker(ticker)
        info = tk.info or {}
    except Exception as exc:
        raise FactExtractionError(f"yfinance error for {ticker}: {exc}") from exc

    flags: List[str] = []
    payload: dict = {
        "as_of_date": as_of_date,
        "currency": str(info.get("currency") or "USD"),
        "analyst_count": _maybe_int(info.get("numberOfAnalystOpinions")),
    }

    for field, key in _FIELD_TO_INFO_KEY.items():
        raw = info.get(key)
        if field in {"currency", "exchange", "sector", "industry"}:
            payload[field] = str(raw) if isinstance(raw, str) and raw else None
        else:
            payload[field] = _maybe_float(raw)
        if payload.get(field) is None and field not in {"currency"}:
            flags.append(f"missing_{field}")

    price = payload.get("price")
    high = payload.get("price_52w_high")
    if price is not None and high and high > 0:
        payload["pct_off_52w_high"] = (price - high) / high

    fcf = _maybe_float(info.get("freeCashflow"))
    mcap = payload.get("market_cap_usd")
    if fcf is not None and mcap and mcap > 0:
        payload["fcf_yield"] = fcf / mcap

    snapshot = FactSnapshot(**payload)
    return snapshot, flags
