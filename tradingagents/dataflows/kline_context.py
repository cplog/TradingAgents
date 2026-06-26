"""K-line context: technical metrics computed from OHLCV data.

Pure math on OHLCV bars — returns, volatility, breakout detection,
support/resistance levels. Market-agnostic (works for US, HK, any market
with daily OHLCV data).

Feeds into analyst prompts and the dimensions system.
"""

from __future__ import annotations

import logging
from math import sqrt
from typing import Any

logger = logging.getLogger(__name__)


def _pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return (a - b) / b * 100


def _stdev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    var = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return sqrt(max(var, 0))


def compute_kline_context(
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    lookback_days: int = 120,
) -> dict[str, Any]:
    """Compute technical context from OHLCV price series.

    Args:
        closes: Close prices, most recent last.
        highs: High prices, most recent last. If omitted, uses closes.
        lows: Low prices, most recent last. If omitted, uses closes.
        lookback_days: Minimum days required for lookback windows.

    Returns:
        Dict with keys: available, current_price, ret_5d, ret_20d, ret_60d,
        volatility_20d, high_20d, low_20d, breakout_state.
    """
    if not closes or len(closes) < 5:
        return {"available": False, "error": "insufficient data"}

    highs = highs or closes
    lows = lows or closes
    current = closes[-1]

    ret_5 = _pct(current, closes[-6] if len(closes) >= 6 else None)
    ret_20 = _pct(current, closes[-21] if len(closes) >= 21 else None)
    ret_60 = _pct(current, closes[-61] if len(closes) >= 61 else None)

    daily_rets: list[float] = []
    for i in range(1, len(closes)):
        base = closes[i - 1]
        if base == 0:
            continue
        daily_rets.append((closes[i] - base) / base * 100)
    vol_20 = _stdev(daily_rets[-20:]) if len(daily_rets) >= 20 else _stdev(daily_rets)

    high_20 = max(highs[-20:]) if len(highs) >= 20 else (max(highs) if highs else None)
    low_20 = min(lows[-20:]) if len(lows) >= 20 else (min(lows) if lows else None)

    # Simple moving average support/resistance
    sma_20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    sma_50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
    sma_200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else None

    breakout = "none"
    if current is not None and high_20 is not None and low_20 is not None:
        if current >= high_20 * 0.998:
            breakout = "near_high_breakout"
        elif current <= low_20 * 1.002:
            breakout = "near_low_breakdown"

    # Trend direction
    trend_state: str = "neutral"
    if sma_20 is not None and sma_50 is not None:
        if sma_20 > sma_50:
            trend_state = "bullish"
        elif sma_20 < sma_50:
            trend_state = "bearish"

    return {
        "available": True,
        "current_price": current,
        "ret_5d": ret_5,
        "ret_20d": ret_20,
        "ret_60d": ret_60,
        "volatility_20d": vol_20,
        "high_20d": high_20,
        "low_20d": low_20,
        "sma_20": sma_20,
        "sma_50": sma_50,
        "sma_200": sma_200,
        "breakout_state": breakout,
        "trend_state": trend_state,
    }


def compute_kline_context_from_df(
    df: "pd.DataFrame",
    close_col: str = "Close",
    high_col: str = "High",
    low_col: str = "Low",
) -> dict[str, Any]:
    """Wrapper that extracts columns from a pandas OHLCV DataFrame."""
    import pandas as pd

    if df is None or df.empty:
        return {"available": False, "error": "empty dataframe"}

    closes = _series_to_floats(df, close_col)
    highs = _series_to_floats(df, high_col)
    lows = _series_to_floats(df, low_col)

    return compute_kline_context(closes, highs, lows)


def _series_to_floats(df: "pd.DataFrame", col: str) -> list[float]:
    import pandas as pd

    if col not in df.columns:
        return []
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    return [float(x) for x in s]


def compute_kline_context_from_csv(csv_str: str) -> dict[str, Any]:
    """Wrapper that parses a CSV string into a DataFrame then computes context."""
    import pandas as pd
    from io import StringIO

    if not csv_str or not csv_str.strip():
        return {"available": False, "error": "empty csv"}

    df = pd.read_csv(StringIO(csv_str))
    if df.empty:
        return {"available": False, "error": "empty dataframe"}

    return compute_kline_context_from_df(df)
