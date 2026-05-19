"""Commentary fallback: when structured output returns None or an unparseable
shape (common on Ollama/OpenRouter free-tier), build_commentary must retry via
plain llm.invoke + JSON parse instead of raising CommentaryError outright.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from api.dimensions.commentary import build_commentary, CommentaryError
from api.dimensions.schemas import (
    DimensionsCommentary, FactorScore, FactorScores, PillarScores,
    MarketPillar, SentimentPillar, NewsPillar, FundamentalsPillar, PillarScore,
    FactSnapshot, StockDimensions,
)


def _ps(s: int = 3) -> PillarScore:
    return PillarScore(score=s, rationale="x")


def _dims() -> StockDimensions:
    return StockDimensions(
        ticker="AAPL", as_of_date="2026-05-13",
        facts=FactSnapshot(as_of_date="2026-05-13", currency="USD"),
        pillar_scores=PillarScores(
            market=MarketPillar(trend=_ps(), momentum=_ps(), volatility_risk=_ps(),
                                setup_quality=_ps()),
            sentiment=SentimentPillar(retail_sentiment=_ps(), social_buzz=_ps(),
                                     consensus_quality=_ps(), narrative_strength=_ps()),
            news=NewsPillar(catalyst_strength=_ps(), macro_alignment=_ps(),
                           headline_quality=_ps(), surprise_risk=_ps()),
            fundamentals=FundamentalsPillar(valuation=_ps(), growth=_ps(),
                                           profitability=_ps(), balance_sheet_strength=_ps()),
        ),
        factor_scores=FactorScores(
            value=FactorScore(score=70.0), growth=FactorScore(score=60.0),
            quality=FactorScore(score=80.0), momentum=FactorScore(score=55.0),
            low_risk=FactorScore(score=40.0), sentiment=FactorScore(score=50.0),
        ),
        dimensions_version="1.0.0",
    )


_VALID_JSON = json.dumps({
    "alignment": "aligned",
    "supporting_dimensions": ["value", "quality"],
    "conflicting_dimensions": [],
    "risk_flags": ["elevated_beta"],
    "summary": "Value/quality scores back the Buy.",
})


def _make_llm(structured_result, fallback_result):
    """Build a fake LLM whose structured invoke returns ``structured_result``
    and whose plain ``invoke`` returns ``fallback_result``."""
    structured = MagicMock()
    structured.invoke = MagicMock(return_value=structured_result)
    fake_llm = MagicMock()
    fake_llm.with_structured_output = MagicMock(return_value=structured)
    fake_llm.invoke = MagicMock(return_value=fallback_result)
    return fake_llm


def test_fallback_when_structured_invoke_raises():
    """OpenRouter free/thinking models often throw on with_structured_output.invoke."""
    parsed_error = (
        "Structured Output response does not have a 'parsed' field nor a 'refusal' field"
    )

    class Boom:
        def invoke(self, _m):
            raise RuntimeError(parsed_error)

    fake_llm = MagicMock()
    fake_llm.with_structured_output = MagicMock(return_value=Boom())
    fake_llm.invoke = MagicMock(return_value=SimpleNamespace(content=_VALID_JSON))

    out = build_commentary(dimensions=_dims(), pm_decision_text="Buy.", llm=fake_llm)
    assert out.alignment == "aligned"
    fake_llm.invoke.assert_called_once()


def test_fallback_raises_when_structured_invoke_raises_and_plain_invoke_fails():
    class Boom:
        def invoke(self, _m):
            raise RuntimeError("structured path broken")

    fake_llm = MagicMock()
    fake_llm.with_structured_output = MagicMock(return_value=Boom())
    fake_llm.invoke = MagicMock(return_value=SimpleNamespace(content="not json"))

    with pytest.raises(CommentaryError, match="Commentary fallback failed after structured invoke error"):
        build_commentary(dimensions=_dims(), pm_decision_text="Buy.", llm=fake_llm)


    fake_llm = _make_llm(
        structured_result=None,
        fallback_result=SimpleNamespace(content=_VALID_JSON),
    )
    out = build_commentary(dimensions=_dims(), pm_decision_text="Buy.", llm=fake_llm)
    assert out.alignment == "aligned"
    assert "value" in out.supporting_dimensions
    fake_llm.invoke.assert_called_once()


def test_fallback_tolerates_prose_before_json():
    text = "Here is the JSON you asked for:\n```json\n" + _VALID_JSON + "\n```\nDone."
    fake_llm = _make_llm(
        structured_result=None,
        fallback_result=SimpleNamespace(content=text),
    )
    out = build_commentary(dimensions=_dims(), pm_decision_text="Buy.", llm=fake_llm)
    assert out.alignment == "aligned"


def test_fallback_raises_with_specific_error_when_both_paths_fail():
    fake_llm = _make_llm(
        structured_result=None,
        fallback_result=SimpleNamespace(content="not json at all, just prose"),
    )
    with pytest.raises(CommentaryError, match="Commentary fallback failed"):
        build_commentary(dimensions=_dims(), pm_decision_text="Buy.", llm=fake_llm)


def test_fallback_used_when_structured_returns_plain_dict():
    fake_llm = _make_llm(
        structured_result={"alignment": "partial", "supporting_dimensions": [],
                           "conflicting_dimensions": [], "risk_flags": [],
                           "summary": "ok"},
        fallback_result=SimpleNamespace(content=_VALID_JSON),
    )
    out = build_commentary(dimensions=_dims(), pm_decision_text="x", llm=fake_llm)
    # dict was coercible — no fallback needed
    assert out.alignment == "partial"
    fake_llm.invoke.assert_not_called()
