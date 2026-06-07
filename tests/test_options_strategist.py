"""Unit tests for the Options Strategist agent and schema rendering."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.agents.schemas import (
    OptionsLeg,
    OptionsRecommendation,
    render_options_recommendation,
)
from tradingagents.agents.options_strategist.options_strategist import (
    _atm_slice,
    _build_chain_markdown,
    _extract_vol_metrics_from_dimensions,
    _pick_expiration,
    create_options_strategist,
)


def test_render_options_recommendation():
    rec = OptionsRecommendation(
        strategy_name="Bull Call Spread",
        directional_bias="bullish",
        underlying_action="Buy at $170",
        legs=[
            OptionsLeg(side="buy", option_type="call", strike=170, expiration_dte=30, expiration_date="2026-07-17"),
            OptionsLeg(side="sell", option_type="call", strike=180, expiration_dte=30, expiration_date="2026-07-17"),
        ],
        max_risk="Limited to $2.00 debit",
        max_reward="$8.00",
        breakeven_at_expiry="$172.00",
        rationale="PM is Overweight with $180 target. IV is average.",
        alternative="Long shares if IV spikes",
        iv_context="IV at 30th percentile — cheap enough for debit spreads.",
    )
    md = render_options_recommendation(rec)
    assert "Bull Call Spread" in md
    assert "| 1 | buy | call | 170.0 | 2026-07-17 |" in md
    assert "| 2 | sell | call | 180.0 | 2026-07-17 |" in md
    assert "Max Risk**" in md
    assert "Max Reward**" in md
    assert "Breakeven at Expiry**" in md
    assert "IV Context**" in md
    assert "Alternative**" in md


def test_render_options_recommendation_minimal():
    rec = OptionsRecommendation(
        strategy_name="No suitable options",
        directional_bias="neutral",
        underlying_action="Hold",
        legs=[],
        rationale="No options chain available for this ticker.",
        alternative="Use underlying equity only.",
    )
    md = render_options_recommendation(rec)
    assert "No suitable options" in md
    assert "Legs" not in md
    assert "Alternative**" in md


def test_pick_expiration():
    import datetime
    today = datetime.date.today()
    exp1 = (today + datetime.timedelta(days=14)).isoformat()
    exp2 = (today + datetime.timedelta(days=30)).isoformat()
    exp3 = (today + datetime.timedelta(days=60)).isoformat()
    assert _pick_expiration([exp1, exp2, exp3], min_dte=21) == exp2
    assert _pick_expiration([exp1], min_dte=21) == exp1  # fallback


def test_pick_expiration_empty():
    assert _pick_expiration([], min_dte=21) is None


def test_atm_slice():
    chain = {
        "underlying_price": 150.0,
        "calls": [
            {"strike": 140.0}, {"strike": 145.0}, {"strike": 150.0},
            {"strike": 155.0}, {"strike": 160.0}, {"strike": 165.0},
        ],
        "puts": [
            {"strike": 140.0}, {"strike": 145.0}, {"strike": 150.0},
            {"strike": 155.0}, {"strike": 160.0}, {"strike": 165.0},
        ],
    }
    sliced = _atm_slice(chain, n=4)
    assert len(sliced["calls"]) == 4
    assert len(sliced["puts"]) == 4
    strikes = [c["strike"] for c in sliced["calls"]]
    assert 150.0 in strikes


def test_build_chain_markdown():
    chain = {
        "underlying_price": 150.0,
        "expiration": "2026-07-17",
        "calls": [
            {"strike": 150.0, "bid": 4.9, "ask": 5.1, "impliedVolatility": 0.30, "volume": 100},
        ],
        "puts": [
            {"strike": 150.0, "bid": 3.9, "ask": 4.1, "impliedVolatility": 0.32, "volume": 80},
        ],
    }
    md = _build_chain_markdown(chain)
    assert "150.0" in md
    assert "Call Bid" in md
    assert "Put Bid" in md


def test_extract_vol_metrics_from_dimensions():
    dim = "- realized_vol_30d: 0.28\n- beta: 1.2\n- rsi_14: 62\n- low_risk factor: 45"
    out = _extract_vol_metrics_from_dimensions(dim)
    assert "realized_vol_30d" in out
    assert "beta" in out
    assert "rsi_14" in out


def test_extract_vol_metrics_empty():
    assert _extract_vol_metrics_from_dimensions("") == ""
    assert _extract_vol_metrics_from_dimensions("price: 100\nmarket_cap: 1T") == ""


def test_create_options_strategist_node():
    """Smoke test: the node factory returns a callable and runs with mocked LLM + data."""
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured

    # Mock LLM response
    rec = OptionsRecommendation(
        strategy_name="Long Call",
        directional_bias="bullish",
        underlying_action="Buy",
        legs=[OptionsLeg(side="buy", option_type="call", strike=150, expiration_dte=30)],
        rationale="Bullish setup.",
    )
    mock_structured.invoke.return_value = rec

    node = create_options_strategist(mock_llm)

    state = {
        "company_of_interest": "AAPL",
        "instrument_context": "AAPL - Apple Inc.",
        "final_trade_decision": "**Rating**: Buy\n\n**Executive Summary**: Bullish.",
        "trader_investment_plan": "**Action**: Buy\n\n**Entry Price**: 150",
        "execution_context": "Live quote: 149.50",
        "dimensions_summary": "- realized_vol_30d: 0.28\n- beta: 1.2",
    }

    with patch(
        "tradingagents.agents.options_strategist.options_strategist.get_options_expirations",
        return_value=["2026-07-17", "2026-08-21"],
    ), patch(
        "tradingagents.agents.options_strategist.options_strategist.get_options_chain",
        return_value={
            "underlying_price": 150.0,
            "expiration": "2026-07-17",
            "calls": [{"strike": 150.0, "bid": 4.9, "ask": 5.1, "impliedVolatility": 0.30, "volume": 100}],
            "puts": [{"strike": 150.0, "bid": 3.9, "ask": 4.1, "impliedVolatility": 0.32, "volume": 80}],
        },
    ):
        result = node(state)

    assert "options_recommendation" in result
    assert "Long Call" in result["options_recommendation"]
    assert result["options_chain_snapshot"] is not None


def test_create_options_strategist_no_expirations():
    """Graceful fallback when no options expirations exist."""
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured

    rec = OptionsRecommendation(
        strategy_name="No suitable options",
        directional_bias="neutral",
        underlying_action="Hold",
        legs=[],
        rationale="No options available.",
        alternative="Use underlying equity only.",
    )
    mock_structured.invoke.return_value = rec

    node = create_options_strategist(mock_llm)

    state = {
        "company_of_interest": "AAPL",
        "instrument_context": "AAPL - Apple Inc.",
        "final_trade_decision": "**Rating**: Buy",
        "trader_investment_plan": "**Action**: Buy",
    }

    with patch(
        "tradingagents.agents.options_strategist.options_strategist.get_options_expirations",
        return_value=[],
    ):
        result = node(state)

    assert "options_recommendation" in result
    assert "No suitable options" in result["options_recommendation"]
    assert result["options_chain_snapshot"] is None
