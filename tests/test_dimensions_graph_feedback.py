"""Tests for compact dimensions summary and graph snapshot wiring."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

from api.dimensions.schemas import (
    FactSnapshot,
    FactorScore,
    FactorScores,
    FundamentalsPillar,
    MarketPillar,
    NewsPillar,
    PillarScore,
    PillarScores,
    SentimentPillar,
    StockDimensions,
)
from tradingagents.agents.dimensions_snapshot import create_dimensions_snapshot_node
from tradingagents.agents.utils.dimensions_summary import render_compact_dimensions_summary


def _ps(s=3):
    return PillarScore(score=s, rationale="x")


def _dim(ticker="AAPL"):
    return StockDimensions(
        ticker=ticker,
        as_of_date="2026-05-13",
        facts=FactSnapshot(as_of_date="2026-05-13", currency="USD"),
        pillar_scores=PillarScores(
            market=MarketPillar(
                trend=_ps(), momentum=_ps(), volatility_risk=_ps(), setup_quality=_ps()
            ),
            sentiment=SentimentPillar(
                retail_sentiment=_ps(),
                social_buzz=_ps(),
                consensus_quality=_ps(),
                narrative_strength=_ps(),
            ),
            news=NewsPillar(
                catalyst_strength=_ps(),
                macro_alignment=_ps(),
                headline_quality=_ps(),
                surprise_risk=_ps(),
            ),
            fundamentals=FundamentalsPillar(
                valuation=_ps(),
                growth=_ps(),
                profitability=_ps(),
                balance_sheet_strength=_ps(),
            ),
        ),
        factor_scores=FactorScores(
            value=FactorScore(score=70.0),
            growth=FactorScore(score=60.0),
            quality=FactorScore(score=80.0),
            momentum=FactorScore(score=55.0),
            low_risk=FactorScore(score=40.0),
            sentiment=FactorScore(score=50.0),
        ),
        dimensions_version="1.0.0",
    )


def test_render_compact_dimensions_summary_contains_factors():
    payload = _dim("NVDA").model_dump()
    text = render_compact_dimensions_summary(payload)
    assert "NVDA" in text
    assert "value" in text.lower()


def test_build_result_dimensions_in_graph_flag(tmp_path: Path):
    from api.reports import build_result

    cfg = {"results_dir": str(tmp_path)}
    fs = {
        "dimensions_snapshot_json": json.dumps(_dim().model_dump(), ensure_ascii=False),
        "market_report": "mk",
    }
    r = build_result(fs, "Buy", "AAPL", "2026-05-13", cfg)
    assert r.get("dimensions_in_graph") is True

    fs2 = {"market_report": "mk"}
    r2 = build_result(fs2, "Buy", "AAPL", "2026-05-13", cfg)
    assert r2.get("dimensions_in_graph") is False


def test_dimensions_snapshot_node_success(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "api.dimensions.builder.build_dimensions",
        lambda **kwargs: _dim("TSLA"),
    )
    node = create_dimensions_snapshot_node(
        MagicMock(),
        {
            "dimensions_enabled": True,
            "dimensions_in_graph": True,
            "data_cache_dir": str(tmp_path),
        },
    )
    out = node(
        {
            "company_of_interest": "TSLA",
            "trade_date": "2026-05-13",
            "market_report": "m",
            "sentiment_report": "s",
            "news_report": "n",
            "fundamentals_report": "f",
        }
    )
    assert out["dimensions_error"] == ""
    assert "TSLA" in out["dimensions_summary"]
    body = json.loads(out["dimensions_snapshot_json"])
    assert body["ticker"] == "TSLA"


def test_dimensions_snapshot_node_skips_when_disabled():
    node = create_dimensions_snapshot_node(
        MagicMock(),
        {"dimensions_enabled": False, "dimensions_in_graph": True},
    )
    out = node({"company_of_interest": "X", "trade_date": "2026-05-13"})
    assert out == {
        "dimensions_summary": "",
        "dimensions_error": "",
        "dimensions_snapshot_json": "",
    }


def test_portfolio_manager_prompt_includes_dimensions_summary():
    from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

    state = {
        "company_of_interest": "AAPL",
        "investment_plan": "plan",
        "trader_investment_plan": "trade",
        "past_context": "",
        "dimensions_summary": "FACTOR value: 42",
        "risk_debate_state": {
            "history": "h",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "latest_speaker": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "judge_decision": "",
            "count": 0,
        },
    }
    llm = MagicMock()
    structured = MagicMock()
    structured.with_structured_output.return_value = MagicMock()
    llm.with_structured_output.return_value = structured
    pm_inner = create_portfolio_manager(llm)
    with mock.patch(
        "tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext",
        return_value="decision",
    ) as p:
        pm_inner(state)
    call_prompt = p.call_args[0][2]
    assert "FACTOR value: 42" in call_prompt
    assert "align" in call_prompt.lower()
