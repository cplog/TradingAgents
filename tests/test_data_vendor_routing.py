"""Unit tests for multi-vendor stock routing and Finnhub helpers."""

from unittest.mock import patch

import pytest

from tradingagents.dataflows import catalog
from tradingagents.dataflows import interface as iface
from tradingagents.dataflows.vendor_errors import DataVendorUnavailable


@pytest.mark.unit
def test_catalog_maps_methods_to_categories():
    assert catalog.get_category_for_method("get_stock_data") == "core_stock_apis"
    assert catalog.get_category_for_method("query_cached_ohlcv") == "core_stock_apis"
    assert catalog.get_category_for_method("get_news") == "news_data"
    assert catalog.get_category_for_method("fetch_hot_news_board") == "news_data"
    assert catalog.get_category_for_method("search_data_cache_news") == "news_data"
    assert catalog.get_category_for_method("get_prediction_market_snapshot") == "news_data"
    assert catalog.get_category_for_method("get_macro_data") == "macro_data"
    assert "core_stock_apis" in catalog.TOOLS_CATEGORIES


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


@pytest.mark.unit
def test_route_macro_lists_prior_vendor_error_when_chain_exhausted():
    """AKShare-only tools return a markdown hint instead of crashing the agent."""
    cfg = {
        "prefer_free_data_vendors": True,
        "data_vendors": {"macro_data": "akshare"},
        "tool_vendors": {},
    }
    old = iface.VENDOR_METHODS["list_akshare_endpoints"]
    try:
        iface.VENDOR_METHODS["list_akshare_endpoints"] = {
            "akshare": lambda **_: (_ for _ in ()).throw(
                DataVendorUnavailable("akshare macro: package not installed")
            )
        }
        with patch.object(iface, "get_config", return_value=cfg):
            out = iface.route_to_vendor("list_akshare_endpoints", prefix="macro_")
    finally:
        iface.VENDOR_METHODS["list_akshare_endpoints"] = old

    assert "package not installed" in out
    assert "list_akshare_endpoints" in out


@pytest.mark.unit
def test_alpha_vantage_missing_key_skips_instead_of_value_error(monkeypatch):
    """Missing ALPHA_VANTAGE_API_KEY must skip AV in the chain, not crash with ValueError."""
    from tradingagents.dataflows import alpha_vantage_common

    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    with pytest.raises(DataVendorUnavailable, match="ALPHA_VANTAGE_API_KEY"):
        alpha_vantage_common.get_api_key()


@pytest.mark.unit
def test_route_stock_data_skips_akshare_auto_fallback_for_us_ticker():
    """US tickers should not hit AKShare unless akshare is explicitly configured."""
    cfg = {
        "prefer_free_data_vendors": True,
        "data_vendors": {"core_stock_apis": "yfinance"},
        "tool_vendors": {},
    }
    calls: list[str] = []

    def fake_yfinance(symbol, start_date, end_date):
        calls.append("yf")
        raise DataVendorUnavailable("yfinance rate limited")

    def fake_akshare(symbol, start_date, end_date):
        calls.append("ak")
        return "should not reach akshare for AAPL"

    def fake_finnhub(symbol, start_date, end_date):
        calls.append("fh")
        return "OK,CSV"

    with patch.object(iface, "get_config", return_value=cfg):
        patched = {
            "yfinance": fake_yfinance,
            "akshare": fake_akshare,
            "finnhub": fake_finnhub,
            "alpha_vantage": lambda *a, **k: (_ for _ in ()).throw(
                DataVendorUnavailable("skip av")
            ),
        }
        old = iface.VENDOR_METHODS["get_stock_data"]
        try:
            iface.VENDOR_METHODS["get_stock_data"] = patched
            out = iface.route_to_vendor(
                "get_stock_data", "AAPL", "2024-01-01", "2024-01-10"
            )
        finally:
            iface.VENDOR_METHODS["get_stock_data"] = old

    assert out == "OK,CSV"
    assert calls == ["yf", "fh"]
    assert "ak" not in calls


@pytest.mark.unit
def test_route_stock_data_skips_alpha_vantage_without_key(monkeypatch):
    cfg = {
        "prefer_free_data_vendors": True,
        "data_vendors": {"core_stock_apis": "yfinance,finnhub,alpha_vantage"},
        "tool_vendors": {},
    }
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)

    def yf_empty(*_a, **_k):
        return "No data found for symbol 'AAPL' between 2024-01-01 and 2024-01-05"

    old = iface.VENDOR_METHODS["get_stock_data"]
    try:
        iface.VENDOR_METHODS["get_stock_data"] = {
            "yfinance": yf_empty,
            "finnhub": old["finnhub"],
            "alpha_vantage": old["alpha_vantage"],
        }
        with patch.object(iface, "get_config", return_value=cfg):
            with pytest.raises(RuntimeError, match="ALPHA_VANTAGE_API_KEY") as ei:
                iface.route_to_vendor(
                    "get_stock_data", "AAPL", "2024-01-01", "2024-01-05"
                )
    finally:
        iface.VENDOR_METHODS["get_stock_data"] = old

    assert not isinstance(ei.value.__cause__, ValueError)
