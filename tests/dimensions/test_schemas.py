import pytest
from pydantic import ValidationError

from api.dimensions.schemas import (
    FactSnapshot, PillarScore, PillarScores, MarketPillar, SentimentPillar,
    NewsPillar, FundamentalsPillar, FactorScore, FactorScores, StockDimensions,
    DimensionsCommentary,
)
from api.dimensions.version import DIMENSIONS_VERSION


def test_pillar_score_validates_range():
    PillarScore(score=1, rationale="ok")
    PillarScore(score=5, rationale="ok")
    with pytest.raises(ValidationError):
        PillarScore(score=0, rationale="too low")
    with pytest.raises(ValidationError):
        PillarScore(score=6, rationale="too high")


def test_factor_score_allows_null():
    fs = FactorScore(score=None, inputs={"reason": "no_inputs"})
    assert fs.score is None


def test_factor_score_validates_range():
    FactorScore(score=0.0, inputs={})
    FactorScore(score=100.0, inputs={})
    with pytest.raises(ValidationError):
        FactorScore(score=-1.0, inputs={})
    with pytest.raises(ValidationError):
        FactorScore(score=101.0, inputs={})


def _ps(score=3, why="ok"):
    return PillarScore(score=score, rationale=why)


def test_stock_dimensions_roundtrip():
    sd = StockDimensions(
        ticker="AAPL",
        as_of_date="2026-05-13",
        facts=FactSnapshot(as_of_date="2026-05-13", currency="USD"),
        pillar_scores=PillarScores(
            market=MarketPillar(trend=_ps(), momentum=_ps(), volatility_risk=_ps(), setup_quality=_ps()),
            sentiment=SentimentPillar(retail_sentiment=_ps(), social_buzz=_ps(),
                                     consensus_quality=_ps(), narrative_strength=_ps()),
            news=NewsPillar(catalyst_strength=_ps(), macro_alignment=_ps(),
                           headline_quality=_ps(), surprise_risk=_ps()),
            fundamentals=FundamentalsPillar(valuation=_ps(), growth=_ps(),
                                           profitability=_ps(), balance_sheet_strength=_ps()),
        ),
        factor_scores=FactorScores(
            value=FactorScore(score=72.0, inputs={"weight_valuation": 0.5}),
            growth=FactorScore(score=60.0, inputs={}),
            quality=FactorScore(score=80.0, inputs={}),
            momentum=FactorScore(score=55.0, inputs={}),
            low_risk=FactorScore(score=40.0, inputs={}),
            sentiment=FactorScore(score=50.0, inputs={}),
        ),
        dimensions_version=DIMENSIONS_VERSION,
        peer_universe_id="sector:Technology|industry:Software",
        data_quality_flags=[],
    )
    dumped = sd.model_dump()
    assert dumped["ticker"] == "AAPL"
    restored = StockDimensions.model_validate(dumped)
    assert restored.factor_scores.value.score == 72.0


def test_commentary_alignment_literal():
    DimensionsCommentary(
        alignment="aligned",
        supporting_dimensions=["value"],
        conflicting_dimensions=[],
        risk_flags=[],
        summary="ok",
    )
    with pytest.raises(ValidationError):
        DimensionsCommentary(
            alignment="kinda",  # type: ignore[arg-type]
            supporting_dimensions=[], conflicting_dimensions=[], risk_flags=[], summary="x",
        )


def test_version_is_semver_one_zero_zero():
    assert DIMENSIONS_VERSION == "1.0.0"
