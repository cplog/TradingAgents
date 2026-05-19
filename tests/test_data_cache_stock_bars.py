"""OHLCV cache: parse, autocache, read."""

from __future__ import annotations

import tempfile

import pytest

from tradingagents.dataflows.cache.repository import (
    fetch_cached_stock_bars,
    maybe_autocache_stock_bars_from_payload,
    upsert_stock_bars,
)
from tradingagents.dataflows.cache.stock_csv import parse_stock_data_csv_payload


@pytest.mark.unit
def test_parse_yfinance_style_csv():
    payload = (
        "# Stock data for DEMO from 2024-01-01 to 2024-01-05\n"
        "# Total records: 2\n\n"
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        "2024-01-02,10.0,11.0,9.5,10.5,10.5,1000000\n"
        "2024-01-03,10.5,12.0,10.4,11.5,11.5,1100000\n"
    )
    rows = parse_stock_data_csv_payload(payload)
    assert len(rows) == 2
    assert rows[0]["bar_date"] == "2024-01-02"
    assert rows[1]["close"] == 11.5
    assert rows[1]["change_pct"] is not None


@pytest.mark.unit
def test_autocache_sqlite_roundtrip():
    sample = (
        "# Stock data for XYZ\n"
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        "2024-06-01,1,2,0.5,1.5,1.5,100\n"
    )
    with tempfile.TemporaryDirectory() as td:
        cfg = {
            "data_cache_backend": "sqlite",
            "data_cache_dir": td,
            "data_cache_sqlite_filename": "bars.db",
            "data_cache_auto_stock_bars": True,
            "data_cache_stock_vendor_tag": "unit_test",
            "data_vendors": {"core_stock_apis": "yfinance"},
            "tool_vendors": {},
        }
        n = maybe_autocache_stock_bars_from_payload(
            cfg, "XYZ", "2024-05-01", "2024-07-01", sample
        )
        assert n == 1
        rows = fetch_cached_stock_bars(cfg, "XYZ", "2024-05-01", "2024-07-01")
        assert len(rows) == 1
        assert rows[0]["vendor"] == "unit_test"


@pytest.mark.unit
def test_upsert_overwrites_same_day():
    with tempfile.TemporaryDirectory() as td:
        cfg = {
            "data_cache_backend": "sqlite",
            "data_cache_dir": td,
            "data_cache_sqlite_filename": "bars2.db",
            "data_cache_stock_vendor_tag": "v",
        }
        rows = [
            {
                "bar_date": "2024-01-02",
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "volume": 100.0,
                "change_pct": 1.0,
            }
        ]
        assert upsert_stock_bars(cfg, "AB", "v", rows) == 1
        rows2 = [
            {
                "bar_date": "2024-01-02",
                "open": 2.0,
                "high": 3.0,
                "low": 1.0,
                "close": 2.5,
                "volume": 200.0,
                "change_pct": 2.0,
            }
        ]
        assert upsert_stock_bars(cfg, "AB", "v", rows2) == 1
        out = fetch_cached_stock_bars(cfg, "AB", "2024-01-01", "2024-01-10")
        assert len(out) == 1
        assert out[0]["close"] == 2.5
