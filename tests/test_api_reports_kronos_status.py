"""When kronos_report is empty, surfacing the typed kronos_status field
(populated by api.jobs._propagate_sync) replaces the generic
"model still had pending tool calls" message with the actual cause —
e.g. ``load_failed``, ``disabled``, ``insufficient_data``.
"""
from __future__ import annotations

import pytest

from api.reports import build_result


def _base_state(kronos_status: str | None) -> dict:
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
    if kronos_status is not None:
        fs["kronos_status"] = kronos_status
    return fs


@pytest.mark.unit
def test_kronos_empty_with_load_failed_surfaces_torch_hint(tmp_path):
    cfg = {"results_dir": str(tmp_path)}
    r = build_result(
        _base_state("load_failed"), "Hold", "AAPL", "2026-05-19", cfg,
        selected_analysts=["market", "kronos"],
    )
    cov = r["analyst_coverage"]["kronos"]
    assert cov["status"] == "empty"
    assert cov["kronos_status"] == "load_failed"
    assert "torch" in cov["detail"].lower()
    assert "pending tool calls" not in cov["detail"].lower()
    body = r["reports"]["kronos"]
    assert "torch" in body.lower()


@pytest.mark.unit
def test_kronos_empty_with_disabled_status(tmp_path):
    cfg = {"results_dir": str(tmp_path)}
    r = build_result(
        _base_state("disabled"), "Hold", "AAPL", "2026-05-19", cfg,
        selected_analysts=["market", "kronos"],
    )
    cov = r["analyst_coverage"]["kronos"]
    assert cov["kronos_status"] == "disabled"
    assert "disabled" in cov["detail"].lower()


@pytest.mark.unit
def test_kronos_empty_with_insufficient_data(tmp_path):
    cfg = {"results_dir": str(tmp_path)}
    r = build_result(
        _base_state("insufficient_data"), "Hold", "AAPL", "2026-05-19", cfg,
        selected_analysts=["market", "kronos"],
    )
    cov = r["analyst_coverage"]["kronos"]
    assert cov["kronos_status"] == "insufficient_data"
    assert "ohlcv" in cov["detail"].lower() or "history" in cov["detail"].lower()


@pytest.mark.unit
def test_kronos_empty_without_status_falls_back_to_generic(tmp_path):
    """No kronos_status key present (e.g. legacy job snapshot) — fall back
    to the existing generic explanation to preserve back-compat."""
    cfg = {"results_dir": str(tmp_path)}
    r = build_result(
        _base_state(None), "Hold", "AAPL", "2026-05-19", cfg,
        selected_analysts=["market", "kronos"],
    )
    cov = r["analyst_coverage"]["kronos"]
    assert cov["status"] == "empty"
    assert "kronos_status" not in cov
    assert "pending tool calls" in cov["detail"]


@pytest.mark.unit
def test_kronos_ok_when_report_present_ignores_status(tmp_path):
    cfg = {"results_dir": str(tmp_path)}
    fs = _base_state("ok")
    fs["kronos_report"] = "### Kronos forecast\n..."
    r = build_result(
        fs, "Hold", "AAPL", "2026-05-19", cfg,
        selected_analysts=["market", "kronos"],
    )
    cov = r["analyst_coverage"]["kronos"]
    assert cov["status"] == "ok"
    assert "kronos_status" not in cov
