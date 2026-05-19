"""Tests for api/kronos/ohlcv.py — yfinance-backed OHLCV fetcher."""
from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from api.kronos.errors import InsufficientData
from api.kronos.ohlcv import fetch_ohlcv


def _make_yf_frame(n_rows: int) -> pd.DataFrame:
    """Build a yfinance-style DataFrame with a DatetimeIndex."""
    dates = pd.date_range(end="2026-05-18", periods=n_rows, freq="B")
    return pd.DataFrame(
        {
            "Open": [100.0 + i * 0.1 for i in range(n_rows)],
            "High": [101.0 + i * 0.1 for i in range(n_rows)],
            "Low": [99.0 + i * 0.1 for i in range(n_rows)],
            "Close": [100.5 + i * 0.1 for i in range(n_rows)],
            "Volume": [1_000_000.0 + i for i in range(n_rows)],
        },
        index=dates,
    )


def test_fetch_ohlcv_happy_path():
    fake_df = _make_yf_frame(250)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = fake_df

    with patch("api.kronos.ohlcv.yf.Ticker", return_value=fake_ticker):
        out = fetch_ohlcv("AAPL", "2026-05-19", lookback=200)

    assert len(out) == 200
    assert set(out.columns) >= {
        "open", "high", "low", "close", "volume", "amount", "timestamps"
    }
    assert out["amount"].iloc[0] == pytest.approx(
        out["close"].iloc[0] * out["volume"].iloc[0]
    )
    assert pd.api.types.is_datetime64_any_dtype(out["timestamps"])
    _, kwargs = fake_ticker.history.call_args
    assert kwargs.get("auto_adjust") is False
    assert kwargs.get("interval") == "1d"


def test_fetch_ohlcv_insufficient_data_raises():
    fake_df = _make_yf_frame(50)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = fake_df

    with patch("api.kronos.ohlcv.yf.Ticker", return_value=fake_ticker):
        with pytest.raises(InsufficientData) as exc:
            fetch_ohlcv("AAPL", "2026-05-19", lookback=200)
    assert "50" in str(exc.value)
    assert "200" in str(exc.value)


def test_fetch_ohlcv_empty_response_raises():
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = pd.DataFrame()
    with patch("api.kronos.ohlcv.yf.Ticker", return_value=fake_ticker):
        with pytest.raises(InsufficientData):
            fetch_ohlcv("XYZ", "2026-05-19", lookback=200)


def test_fetch_ohlcv_preserves_ticker_suffix():
    """HK / A-share style tickers must be passed through to yfinance verbatim."""
    fake_df = _make_yf_frame(250)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = fake_df

    with patch("api.kronos.ohlcv.yf.Ticker", return_value=fake_ticker) as ctor:
        fetch_ohlcv("0700.HK", "2026-05-19", lookback=200)
    ctor.assert_called_once_with("0700.HK")
