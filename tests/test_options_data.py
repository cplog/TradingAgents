"""Unit tests for the yfinance options data fetcher."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.dataflows.options_data import (
    _clean_option_row,
    get_options_chain,
    get_options_context,
    get_options_expirations,
)


class FakeOptionRow:
    def __init__(self, **kwargs):
        self._data = kwargs

    def get(self, key, default=None):
        return self._data.get(key, default)


class FakeOptionChain:
    def __init__(self, calls_df=None, puts_df=None):
        self.calls = calls_df
        self.puts = puts_df


class FakeDataFrame:
    def __init__(self, rows):
        self._rows = rows
        self.empty = not rows

    def iterrows(self):
        for i, row in enumerate(self._rows):
            yield i, row


class FakeTicker:
    def __init__(self, expirations=None, info=None, chain=None, calendar=None):
        self._exp = expirations or []
        self._info = info or {}
        self._chain = chain
        self._calendar = calendar

    @property
    def info(self):
        return self._info

    @property
    def options(self):
        return self._exp

    @property
    def calendar(self):
        return self._calendar

    def option_chain(self, expiration):
        return self._chain


def test_clean_option_row_full():
    row = FakeOptionRow(
        strike=150.0,
        lastPrice=5.2,
        bid=5.0,
        ask=5.4,
        impliedVolatility=0.35,
        volume=1200,
        openInterest=5000,
    )
    out = _clean_option_row(row)
    assert out == {
        "strike": 150.0,
        "lastPrice": 5.2,
        "bid": 5.0,
        "ask": 5.4,
        "impliedVolatility": 0.35,
        "volume": 1200,
        "openInterest": 5000,
    }


def test_clean_option_row_none():
    assert _clean_option_row(None) is None


def test_get_options_expirations_success():
    fake = FakeTicker(expirations=["2026-07-17", "2026-08-21"])
    with patch(
        "tradingagents.dataflows.options_data._yf_ticker", return_value=fake
    ):
        assert get_options_expirations("AAPL") == ["2026-07-17", "2026-08-21"]


def test_get_options_expirations_failure():
    with patch(
        "tradingagents.dataflows.options_data._yf_ticker",
        side_effect=RuntimeError("network"),
    ):
        assert get_options_expirations("AAPL") == []


def test_get_options_chain_success():
    calls = FakeDataFrame(
        [
            FakeOptionRow(strike=150.0, lastPrice=5.0, bid=4.9, ask=5.1, impliedVolatility=0.30, volume=100, openInterest=200),
            FakeOptionRow(strike=155.0, lastPrice=3.0, bid=2.9, ask=3.1, impliedVolatility=0.28, volume=50, openInterest=100),
        ]
    )
    puts = FakeDataFrame(
        [
            FakeOptionRow(strike=150.0, lastPrice=4.0, bid=3.9, ask=4.1, impliedVolatility=0.32, volume=80, openInterest=150),
        ]
    )
    chain = FakeOptionChain(calls_df=calls, puts_df=puts)
    fake = FakeTicker(info={"regularMarketPrice": 152.0}, chain=chain)
    with patch(
        "tradingagents.dataflows.options_data._yf_ticker", return_value=fake
    ):
        out = get_options_chain("AAPL", "2026-07-17")
    assert out["underlying_price"] == 152.0
    assert len(out["calls"]) == 2
    assert len(out["puts"]) == 1
    assert out["calls"][0]["strike"] == 150.0
    assert "error" not in out or out["error"] is None


def test_get_options_chain_failure():
    with patch(
        "tradingagents.dataflows.options_data._yf_ticker",
        side_effect=RuntimeError("boom"),
    ):
        out = get_options_chain("AAPL", "2026-07-17")
    assert "error" in out
    assert out["calls"] == []
    assert out["puts"] == []


def test_get_options_context_success():
    fake = FakeTicker(
        info={"shortPercentOfFloat": 0.12, "shortRatio": 3.5},
        calendar={
            "Earnings Date": ["2026-07-28"],
            "Ex-Dividend Date": "2026-05-11",
        },
    )
    with patch(
        "tradingagents.dataflows.options_data._yf_ticker", return_value=fake
    ):
        out = get_options_context("AAPL")
    assert out["earnings_date"] == "2026-07-28"
    assert out["ex_dividend_date"] == "2026-05-11"
    assert out["short_percent_float"] == 0.12
    assert out["short_ratio"] == 3.5


def test_get_options_context_failure():
    with patch(
        "tradingagents.dataflows.options_data._yf_ticker",
        side_effect=RuntimeError("network"),
    ):
        out = get_options_context("AAPL")
    assert "error" in out
