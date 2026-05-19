from unittest.mock import MagicMock

import pytest

from api.dimensions.commentary import build_commentary, CommentaryError
from api.dimensions.schemas import (
    DimensionsCommentary, FactorScore, FactorScores, PillarScores,
    MarketPillar, SentimentPillar, NewsPillar, FundamentalsPillar, PillarScore,
    FactSnapshot, StockDimensions,
)


def _ps(s=3):
    return PillarScore(score=s, rationale="x")


def _dims():
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


def _result():
    return DimensionsCommentary(
        alignment="aligned",
        supporting_dimensions=["value", "quality"],
        conflicting_dimensions=[],
        risk_flags=["elevated_beta"],
        summary="PM rating Buy aligns with strong Value (70) and Quality (80).",
    )


def test_build_commentary_returns_parsed_model():
    fake_llm = MagicMock()
    structured = MagicMock()
    structured.invoke = MagicMock(return_value=_result())
    fake_llm.with_structured_output = MagicMock(return_value=structured)

    out = build_commentary(dimensions=_dims(), pm_decision_text="Buy. Strong setup.", llm=fake_llm)
    assert out.alignment == "aligned"
    assert "value" in out.supporting_dimensions


def test_build_commentary_falls_back_when_structured_invoke_raises():
    class Boom:
        def invoke(self, _m):
            raise RuntimeError("provider down")

    fake_llm = MagicMock()
    fake_llm.with_structured_output = MagicMock(return_value=Boom())
    fake_llm.invoke = MagicMock(return_value=type("Msg", (), {"content":
        '{"alignment":"partial","supporting_dimensions":[],'
        '"conflicting_dimensions":[],"risk_flags":[],"summary":"x"}'
    })())
    out = build_commentary(dimensions=_dims(), pm_decision_text="x", llm=fake_llm)
    assert out.alignment == "partial"
    fake_llm.invoke.assert_called_once()


def test_build_commentary_raises_when_both_structured_and_fallback_fail():
    class Boom:
        def invoke(self, _m):
            raise RuntimeError("provider down")
    fake_llm = MagicMock()
    fake_llm.with_structured_output = MagicMock(return_value=Boom())
    fake_llm.invoke = MagicMock(side_effect=RuntimeError("fallback down"))
    with pytest.raises(CommentaryError):
        build_commentary(dimensions=_dims(), pm_decision_text="x", llm=fake_llm)


def test_build_commentary_logs_and_falls_back_when_invoke_returns_none(caplog):
    """Structured returning None must trigger the plain-invoke JSON fallback —
    not raise. Only if the fallback *also* fails do we raise CommentaryError.
    """
    class ReturnsNone:
        def invoke(self, _m):
            return None

    fake_llm = MagicMock()
    fake_llm.with_structured_output = MagicMock(return_value=ReturnsNone())
    # Fallback path: llm.invoke(...) returns prose containing valid JSON.
    fake_llm.invoke = MagicMock(return_value=type("Msg", (), {"content":
        '{"alignment":"partial","supporting_dimensions":[],'
        '"conflicting_dimensions":[],"risk_flags":[],"summary":"x"}'
    })())
    with caplog.at_level("WARNING", logger="api.dimensions.commentary"):
        out = build_commentary(
            dimensions=_dims(), pm_decision_text="Hold.", llm=fake_llm
        )
    assert out.alignment == "partial"
    assert "returned None" in caplog.text
