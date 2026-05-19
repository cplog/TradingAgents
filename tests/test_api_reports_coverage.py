"""API report payload: analyst coverage + empty stubs when analysts are explicit."""
from __future__ import annotations

import pytest

from api.reports import build_result


@pytest.mark.unit
def test_build_result_with_selected_analysts_flags_empty(tmp_path):
    cfg = {"results_dir": str(tmp_path)}
    fs = {
        "market_report": "ok market",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "hot_money_report": "",
        "policy_report": "",
        "lockup_report": "",
        "kronos_report": "",
        "investment_plan": "## Plan",
        "trader_investment_plan": "## Trade",
        "final_trade_decision": "## PM\nHold",
    }
    selected = ["market", "social", "hot_money"]
    r = build_result(fs, "Hold", "NVDA", "2026-05-18", cfg, selected_analysts=selected)
    cov = r.get("analyst_coverage") or {}
    assert cov["market"]["status"] == "ok"
    assert cov["social"]["status"] == "empty"
    assert cov["hot_money"]["status"] == "empty"
    assert "market" in r["reports"] and r["reports"]["market"] == "ok market"
    assert r["reports"]["social"].startswith("**Status:** empty")
    assert r["reports"]["hot_money"].startswith("**Status:** empty")
    assert "research_plan" in r["reports"]


@pytest.mark.unit
def test_build_result_legacy_omits_empty_analyst_reports(tmp_path):
    cfg = {"results_dir": str(tmp_path)}
    fs = {
        "market_report": "m",
        "sentiment_report": "",
        "investment_plan": "plan",
    }
    r = build_result(fs, "Hold", "X", "2026-05-18", cfg, selected_analysts=None)
    assert r.get("analyst_coverage") is None
    assert "market" in r["reports"]
    assert "social" not in r["reports"]
