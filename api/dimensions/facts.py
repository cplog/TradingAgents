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

# Price-history-derived fields are populated separately from `tk.history()`,
# not from `info`. They still need missing-flag treatment when computation
# cannot run (empty history, too few rows, etc.).
_PRICE_HISTORY_FIELDS = (
    "return_1m",
    "return_3m",
    "return_6m",
    "return_12m",
    "realized_vol_30d",
    "rsi_14",
    "avg_daily_dollar_volume_30d",
)


def _compute_return(closes, lookback: int) -> Optional[float]:
    """Return (last_close / close_lookback_ago) - 1, or None if insufficient data."""
    if closes is None or len(closes) <= lookback:
        return None
    try:
        last = float(closes.iloc[-1])
        prior = float(closes.iloc[-1 - lookback])
    except (IndexError, ValueError, TypeError):
        return None
    if not math.isfinite(last) or not math.isfinite(prior) or prior == 0:
        return None
    return (last / prior) - 1.0


def _compute_realized_vol_30d(closes) -> Optional[float]:
    """Annualized stdev of last 30 daily log returns (× sqrt(252))."""
    if closes is None or len(closes) < 31:
        return None
    try:
        import numpy as np
        log_returns = np.log(closes / closes.shift(1)).dropna().iloc[-30:]
        if len(log_returns) < 30:
            return None
        vol = float(log_returns.std(ddof=1) * math.sqrt(252))
    except (ValueError, TypeError, ZeroDivisionError):
        return None
    if not math.isfinite(vol):
        return None
    return vol


def _compute_rsi_14(closes) -> Optional[float]:
    """Standard 14-day RSI using Wilder's smoothing (SMA of gains/losses)."""
    if closes is None or len(closes) < 15:
        return None
    try:
        diffs = closes.diff().dropna()
        if len(diffs) < 14:
            return None
        gains = diffs.clip(lower=0.0).iloc[-14:]
        losses = (-diffs.clip(upper=0.0)).iloc[-14:]
        avg_gain = float(gains.mean())
        avg_loss = float(losses.mean())
    except (ValueError, TypeError):
        return None
    if avg_loss == 0:
        # No losses in the window → RSI is conventionally 100.
        return 100.0 if avg_gain > 0 else None
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    if not math.isfinite(rsi):
        return None
    return rsi


def _compute_avg_dollar_volume_30d(closes, volumes) -> Optional[float]:
    """Mean of (Close × Volume) over the last 30 trading days."""
    if closes is None or volumes is None:
        return None
    if len(closes) < 30 or len(volumes) < 30:
        return None
    try:
        dv = (closes * volumes).iloc[-30:]
        avg = float(dv.mean())
    except (ValueError, TypeError):
        return None
    if not math.isfinite(avg):
        return None
    return avg


def _populate_price_history(payload: dict, history_df) -> None:
    """Fill price-history-derived fields on `payload` in place.

    Leaves any field as None when the calculation cannot run, so the
    subsequent flag-append loop will record `missing_*` flags.
    """
    closes = None
    volumes = None
    if history_df is not None:
        try:
            if "Close" in history_df.columns:
                closes = history_df["Close"].dropna()
            if "Volume" in history_df.columns:
                volumes = history_df["Volume"].dropna()
        except AttributeError:
            closes = None
            volumes = None

    payload["return_1m"] = _compute_return(closes, 21)
    payload["return_3m"] = _compute_return(closes, 63)
    payload["return_6m"] = _compute_return(closes, 126)
    payload["return_12m"] = _compute_return(closes, 252)
    payload["realized_vol_30d"] = _compute_realized_vol_30d(closes)
    payload["rsi_14"] = _compute_rsi_14(closes)
    payload["avg_daily_dollar_volume_30d"] = _compute_avg_dollar_volume_30d(closes, volumes)


def extract_facts(ticker: str, as_of_date: str) -> Tuple[FactSnapshot, List[str]]:
    """Return (FactSnapshot, data_quality_flags). Raises FactExtractionError on yfinance error."""
    try:
        tk = _yf_ticker(ticker)
        info = tk.info or {}
        history_df = tk.history(period="13mo", interval="1d")
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

    # Price-history-derived fields (single tk.history() call above).
    _populate_price_history(payload, history_df)

    # Deferred to follow-up: roic, interest_coverage, revenue_cagr_3y, eps_cagr_3y
    # require additional yfinance calls (financials, balance_sheet). See spec §4.1.

    price = payload.get("price")
    high = payload.get("price_52w_high")
    if price is not None and high and high > 0:
        payload["pct_off_52w_high"] = (price - high) / high

    fcf = _maybe_float(info.get("freeCashflow"))
    mcap = payload.get("market_cap_usd")
    if fcf is not None and mcap and mcap > 0:
        payload["fcf_yield"] = fcf / mcap

    # Flag any source fact field that ended up None. Centralized here so all
    # fields — info-derived, history-derived, and analyst_count — get the
    # same treatment. (`pct_off_52w_high` and `fcf_yield` are derived
    # composites already covered by their inputs' flags, so not re-flagged.)
    flag_fields: List[str] = list(_FIELD_TO_INFO_KEY.keys())
    flag_fields.extend(_PRICE_HISTORY_FIELDS)
    flag_fields.append("analyst_count")
    for field in flag_fields:
        # currency always defaults to "USD"; not flagged.
        if payload.get(field) is None and field not in {"currency"}:
            flags.append(f"missing_{field}")

    snapshot = FactSnapshot(**payload)
    return snapshot, flags
