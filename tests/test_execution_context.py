"""Unit tests for live quote vs plan comparison."""

from __future__ import annotations

import pytest

from datetime import datetime, timezone

from tradingagents.agents.utils.execution_context import (
    compare_live_vs_plan,
    derive_plan_levels,
    parse_md_field,
)


@pytest.mark.unit
def test_parse_md_field_strips_final_proposal_trailer():
    text = "**Position Sizing**: 5-7% of portfolio\n\nFINAL TRANSACTION PROPOSAL: **BUY**"
    assert parse_md_field(text, "Position Sizing") == "5-7% of portfolio"


@pytest.mark.unit
def test_derive_plan_levels_from_reports():
    reports = {
        "trader_plan": "**Action**: Buy\n**Entry Price**: 15.1\n**Stop Loss**: 14.8",
        "portfolio_decision": "**Price Target**: 16.8",
    }
    levels = derive_plan_levels(reports)
    assert levels["entry"] == 15.1
    assert levels["stop_loss"] == 14.8
    assert levels["price_target"] == 16.8


@pytest.mark.unit
def test_compare_below_stop_at_run_time_no_refresh():
    """Price already below stop when analysis ran — warn, don't ask to re-run."""
    levels = {"entry": 15.1, "stop_loss": 14.8, "price_target": 16.8}
    out = compare_live_vs_plan(
        13.1,
        levels,
        run_time_price=13.1,
        completed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    assert out["status"] == "below_stop"
    assert out["suggest_refresh"] is False
    assert "already below" in out["guidance"].lower() or "at analysis time" in out["guidance"].lower()


@pytest.mark.unit
def test_compare_below_stop_price_moved_suggests_refresh():
    levels = {"entry": 15.1, "stop_loss": 14.8, "price_target": 16.8}
    out = compare_live_vs_plan(
        13.1,
        levels,
        run_time_price=15.0,
        completed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    assert out["status"] == "below_stop"
    assert out["suggest_refresh"] is True
    assert "since analysis" in out["guidance"].lower()


@pytest.mark.unit
def test_compare_below_stop():
    levels = {"entry": 15.1, "stop_loss": 14.8, "price_target": 16.8}
    out = compare_live_vs_plan(13.1, levels)
    assert out["status"] == "below_stop"
    assert "invalidated" in out["guidance"].lower()
    assert out["delta_vs_stop_pct"] is not None
    assert out["delta_vs_stop_pct"] < 0


@pytest.mark.unit
def test_compare_in_entry_zone():
    levels = {"entry": 15.1, "stop_loss": 14.8, "price_target": 16.8}
    out = compare_live_vs_plan(15.05, levels)
    assert out["status"] == "in_entry_zone"


@pytest.mark.unit
def test_compare_quote_unavailable():
    levels = {"entry": 15.1, "stop_loss": 14.8, "price_target": 16.8}
    out = compare_live_vs_plan(None, levels)
    assert out["status"] == "quote_unavailable"


@pytest.mark.unit
def test_derive_plan_levels_from_narrative_when_labels_missing():
    reports = {
        "trader_plan": "**Action**: Buy\n**Reasoning**: Accumulate on pull-back.",
        "portfolio_decision": (
            "**Rating**: Buy\n"
            "**Executive Summary**: Add near $12.20 with stop below $11.40 and price target $14.50."
        ),
    }
    levels = derive_plan_levels(reports, reference_price=12.57)
    assert levels["entry"] == 12.2
    assert levels["stop_loss"] == 11.4
    assert levels["price_target"] == 14.5


@pytest.mark.unit
def test_derive_plan_levels_prefers_labeled_fields_over_narrative():
    reports = {
        "trader_plan": "**Entry Price**: 15.1\nAdd near $10.00 in prose.",
        "portfolio_decision": "**Stop Loss**: 14.8",
    }
    levels = derive_plan_levels(reports, reference_price=15.0)
    assert levels["entry"] == 15.1
    assert levels["stop_loss"] == 14.8
