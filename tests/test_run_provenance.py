"""Unit tests for run provenance extraction."""

import pytest

from api.run_provenance import build_run_provenance, format_data_routing, merge_config_snapshot


@pytest.mark.unit
def test_merge_config_snapshot_includes_data_vendors():
    snap = merge_config_snapshot(
        {
            "llm_provider": "openai",
            "deep_think_llm": "gpt-5.4",
            "data_vendors": {"news_data": "yfinance,alpha_vantage"},
            "OPENAI_API_KEY": "secret",
        }
    )
    assert "OPENAI_API_KEY" not in snap
    assert snap["data_vendors"]["news_data"] == "yfinance,alpha_vantage"


@pytest.mark.unit
def test_build_run_provenance_flags_single_vendor():
    prov = build_run_provenance(
        {
            "llm_provider": "google",
            "deep_think_llm": "gemini-3.1-pro-preview",
            "quick_think_llm": "gemini-3-flash-preview",
            "data_vendors": {
                "core_stock_apis": "yfinance",
                "technical_indicators": "yfinance",
                "fundamental_data": "yfinance",
                "news_data": "yfinance",
            },
            "analysts": ["market", "news", "fundamentals"],
        },
        {
            "market": {"status": "ok"},
            "news": {"status": "empty"},
            "fundamentals": {"status": "ok"},
        },
    )
    assert prov["llm_provider"] == "google"
    assert prov["source_pillars"] == 4
    assert prov["vendor_count"] == 1
    assert prov["analysts_ok"] == 2
    assert prov["analysts_empty"] == 1
    assert any("Single data vendor" in w for w in prov["bias_warnings"])


@pytest.mark.unit
def test_format_data_routing_all_same_vendor():
    label = format_data_routing(
        {"data_vendors": {"core_stock_apis": "yfinance", "news_data": "yfinance"}}
    )
    assert "all→yfinance" in label or "yfinance" in label
