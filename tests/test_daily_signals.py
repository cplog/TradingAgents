"""Unit tests for daily Barbell Trend Cloud signal scoring."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from tradingagents.dataflows.daily_signals import compute_overnight_signal


def _make_df(n: int = 80, *, last_close: float = 100.0, last_vol: float = 1_000_000) -> pd.DataFrame:
    dates = pd.date_range(end=pd.Timestamp.today(), periods=n, freq="D")
    close = pd.Series([100.0] * (n - 1) + [last_close], index=dates)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close * 0.99,
            "High": close * 1.02,
            "Low": close * 0.97,
            "Close": close,
            "Volume": [500_000.0] * (n - 1) + [last_vol],
        }
    )


@pytest.mark.unit
def test_high_score_on_panic_with_oversold_bias():
    df = _make_df(last_close=85.0, last_vol=2_000_000)
    spot = {"change_pct": -12.0, "amplitude_pct": 5.0}
    with patch("tradingagents.dataflows.daily_signals.load_ohlcv", return_value=df):
        sig = compute_overnight_signal("AAPL", trade_date="2026-05-23", spot=spot)
    assert sig.flags["drop_ge_10pct"]
    assert sig.score >= 50


@pytest.mark.unit
def test_wide_range_reduces_score():
    df = _make_df(last_close=90.0)
    spot = {"change_pct": -11.0, "amplitude_pct": 12.0}
    with patch("tradingagents.dataflows.daily_signals.load_ohlcv", return_value=df):
        sig = compute_overnight_signal("AAPL", trade_date="2026-05-23", spot=spot)
    assert sig.wide_range is True
    assert sig.flags["amplitude_ok"] is False


@pytest.mark.unit
def test_insufficient_data_raises():
    df = _make_df(n=10)
    with patch("tradingagents.dataflows.daily_signals.load_ohlcv", return_value=df):
        with pytest.raises(Exception):
            compute_overnight_signal("AAPL", trade_date="2026-05-23")
