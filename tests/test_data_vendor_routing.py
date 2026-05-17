"""Unit tests for multi-vendor stock routing and Finnhub helpers."""

from unittest.mock import patch

import pytest

from tradingagents.dataflows import interface as iface
from tradingagents.dataflows.vendor_errors import DataVendorUnavailable


@pytest.mark.unit
def test_route_stock_tries_next_on_yfinance_empty_string():
    cfg = {
        "prefer_free_data_vendors": True,
        "data_vendors": {"core_stock_apis": "yfinance,finnhub"},
        "tool_vendors": {},
    }
    calls: list[str] = []

    def fake_yfinance(symbol, start_date, end_date):
        calls.append("yf")
        return "No data found for symbol 'FAKE' between 2024-01-01 and 2024-01-10"

    def fake_finnhub(symbol, start_date, end_date):
        calls.append("fh")
        return "OK,CSV"

    with patch.object(iface, "get_config", return_value=cfg):
        patched = {
            "yfinance": fake_yfinance,
            "finnhub": fake_finnhub,
            "alpha_vantage": lambda *a, **k: (_ for _ in ()).throw(
                RuntimeError("should not reach av in this test")
            ),
            "akshare": lambda *a, **k: (_ for _ in ()).throw(DataVendorUnavailable("skip")),
            "baostock": lambda *a, **k: (_ for _ in ()).throw(DataVendorUnavailable("skip")),
        }
        old = iface.VENDOR_METHODS["get_stock_data"]
        try:
            iface.VENDOR_METHODS["get_stock_data"] = patched
            out = iface.route_to_vendor(
                "get_stock_data", "FAKE", "2024-01-01", "2024-01-10"
            )
        finally:
            iface.VENDOR_METHODS["get_stock_data"] = old

    assert out == "OK,CSV"
    assert calls == ["yf", "fh"]


@pytest.mark.unit
def test_route_news_tries_next_on_yfinance_no_news():
    cfg = {
        "prefer_free_data_vendors": True,
        "data_vendors": {"news_data": "yfinance,finnhub"},
        "tool_vendors": {},
    }
    calls: list[str] = []

    def fake_yf(t, s, e):
        calls.append("yf")
        return "No news found for TICK between 2024-01-01 and 2024-01-07"

    def fake_fh(t, s, e):
        calls.append("fh")
        return "## News OK"

    patched = {
        "yfinance": fake_yf,
        "finnhub": fake_fh,
        "alpha_vantage": lambda *a, **k: (_ for _ in ()).throw(DataVendorUnavailable("skip")),
    }
    old = iface.VENDOR_METHODS["get_news"]
    try:
        iface.VENDOR_METHODS["get_news"] = patched
        with patch.object(iface, "get_config", return_value=cfg):
            out = iface.route_to_vendor(
                "get_news", "TICK", "2024-01-01", "2024-01-07"
            )
    finally:
        iface.VENDOR_METHODS["get_news"] = old

    assert out == "## News OK"
    assert calls == ["yf", "fh"]


@pytest.mark.unit
def test_finnhub_skips_without_key(monkeypatch):
    from tradingagents.dataflows import finnhub_data

    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with pytest.raises(DataVendorUnavailable, match="FINNHUB_API_KEY"):
        finnhub_data.get_stock_finnhub("AAPL", "2024-01-02", "2024-01-05")


@pytest.mark.unit
def test_route_macro_data_uses_akshare_vendor():
    cfg = {
        "prefer_free_data_vendors": True,
        "data_vendors": {"macro_data": "akshare"},
        "tool_vendors": {},
    }

    old = iface.VENDOR_METHODS["get_macro_data"]
    try:
        iface.VENDOR_METHODS["get_macro_data"] = {
            "akshare": lambda fn, params_json, tail_rows: f"OK:{fn}:{tail_rows}"
        }
        with patch.object(iface, "get_config", return_value=cfg):
            out = iface.route_to_vendor("get_macro_data", "macro_cnbs", "{}", 50)
    finally:
        iface.VENDOR_METHODS["get_macro_data"] = old

    assert out == "OK:macro_cnbs:50"
