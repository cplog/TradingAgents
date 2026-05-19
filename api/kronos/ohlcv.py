"""OHLCV fetcher for Kronos input — wraps yfinance."""
from __future__ import annotations

import pandas as pd
import yfinance as yf

from api.kronos.errors import InsufficientData


def fetch_ohlcv(
    ticker: str,
    trade_date: str,
    lookback: int = 200,
) -> pd.DataFrame:
    """Fetch ``lookback`` daily bars ending on or just before ``trade_date``.

    Args:
        ticker: Symbol passed verbatim to yfinance (e.g. "AAPL", "0700.HK",
            "600519.SS"). Exchange suffixes are preserved.
        trade_date: ISO date used as the (exclusive) right edge of the history
            window — yfinance's ``end`` is exclusive, so we pass ``trade_date+1``.
        lookback: Number of daily bars required. Raises ``InsufficientData`` if
            yfinance returns fewer rows (after dropping weekends/holidays).

    Returns:
        DataFrame with columns ``['timestamps','open','high','low','close',
        'volume','amount']`` and exactly ``lookback`` rows (the tail of what
        yfinance returned). ``amount = close * volume`` since yfinance does
        not expose turnover-in-currency.
    """
    end = pd.to_datetime(trade_date) + pd.Timedelta(days=1)
    buffer_days = int(lookback * 1.6) + 30
    start = end - pd.Timedelta(days=buffer_days)

    raw = yf.Ticker(ticker).history(
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="1d",
        auto_adjust=False,
    )

    if raw is None or raw.empty or len(raw) < lookback:
        n_got = 0 if raw is None or raw.empty else len(raw)
        raise InsufficientData(
            f"yfinance returned {n_got} daily bars for {ticker}, "
            f"need >= {lookback}"
        )

    tail = raw.tail(lookback).copy()
    out = pd.DataFrame(
        {
            "open": tail["Open"].astype(float).values,
            "high": tail["High"].astype(float).values,
            "low": tail["Low"].astype(float).values,
            "close": tail["Close"].astype(float).values,
            "volume": tail["Volume"].astype(float).values,
        }
    )
    out["amount"] = out["close"] * out["volume"]
    out["timestamps"] = pd.to_datetime(tail.index)
    out = out.reset_index(drop=True)
    return out[["timestamps", "open", "high", "low", "close", "volume", "amount"]]
