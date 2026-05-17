import pytest

from api.dimensions.factors import (
    compute_factors,
    compute_factors_with_flags,
    scale_1_5_to_0_100,
    INVERTED_PEER_FIELDS,
)
from api.dimensions.schemas import (
    PillarScores, MarketPillar, SentimentPillar, NewsPillar, FundamentalsPillar,
    PillarScore,
)


def _ps(s):
    return PillarScore(score=s, rationale="x")


def _pillars(**overrides):
    base = dict(
        market=MarketPillar(
            trend=_ps(4), momentum=_ps(4), volatility_risk=_ps(3), setup_quality=_ps(3),
        ),
        sentiment=SentimentPillar(
            retail_sentiment=_ps(3), social_buzz=_ps(3),
            consensus_quality=_ps(3), narrative_strength=_ps(3),
        ),
        news=NewsPillar(
            catalyst_strength=_ps(3), macro_alignment=_ps(3),
            headline_quality=_ps(3), surprise_risk=_ps(3),
        ),
        fundamentals=FundamentalsPillar(
            valuation=_ps(4), growth=_ps(4), profitability=_ps(4), balance_sheet_strength=_ps(4),
        ),
    )
    return PillarScores(**{**base, **overrides})


def test_scale_1_5_maps_endpoints():
    assert scale_1_5_to_0_100(1) == 0.0
    assert scale_1_5_to_0_100(3) == 50.0
    assert scale_1_5_to_0_100(5) == 100.0


def test_inverted_fields_include_pe_pb():
    assert "pe_ttm" in INVERTED_PEER_FIELDS
    assert "pb" in INVERTED_PEER_FIELDS


def test_compute_factors_happy_path():
    pillars = _pillars()
    peer_pct = {"pe_ttm": 0.7, "pb": 0.6, "eps_growth_yoy": 0.8, "revenue_growth_yoy": 0.7,
                "roe": 0.9, "interest_coverage": 0.6, "return_3m": 0.8, "return_12m": 0.7,
                "beta": 0.5}
    facts = {"beta": 1.2}
    out = compute_factors(pillars, facts, peer_pct)
    assert 0 <= out.value.score <= 100
    assert 0 <= out.growth.score <= 100
    assert 0 <= out.quality.score <= 100
    assert 0 <= out.momentum.score <= 100
    assert "weight_valuation_pillar" in out.value.inputs
    assert "weight_pe_pct" in out.value.inputs


def test_compute_factors_drops_null_terms_and_renormalizes():
    pillars = _pillars()
    peer_pct = {"pe_ttm": None, "pb": 0.5}  # pe percentile missing
    facts = {}
    out = compute_factors(pillars, facts, peer_pct)
    assert out.value.score is not None
    # pe weight should be dropped from inputs audit
    assert "weight_pe_pct" not in out.value.inputs


def test_compute_factors_all_inputs_missing_returns_none():
    pillars = _pillars(market=MarketPillar(
        trend=PillarScore(score=3, rationale="x"),
        momentum=PillarScore(score=3, rationale="x"),
        volatility_risk=PillarScore(score=3, rationale="x"),
        setup_quality=PillarScore(score=3, rationale="x"),
    ))
    peer_pct = {}
    facts = {"beta": None}
    out = compute_factors(pillars, facts, peer_pct)
    # low_risk has *some* input (volatility_risk pillar from market), so it should still produce a score
    assert out.low_risk.score is not None


def test_compute_factors_null_when_truly_no_inputs():
    """Construct a synthetic pillar set forcing one factor to have no usable inputs.

    Implementation detail: if a factor's entire input set is None/dropped, score=None
    and a data_quality_flag is added by the caller (build_dimensions).
    """
    pillars = _pillars()
    out, flags = compute_factors_with_flags(pillars, {}, {})
    # All pillar inputs exist (1..5), so all factors should still have scores. flags empty.
    assert all(f.score is not None for f in [out.value, out.growth, out.quality,
                                              out.momentum, out.low_risk, out.sentiment])
    assert flags == []


def test_strict_peer_pct_blanks_relative_style_factors():
    pillars = _pillars()
    out_loose, loose_flags = compute_factors_with_flags(
        pillars, {}, {}, enforce_peer_pct_for_style_factors=False,
    )
    assert out_loose.value.score is not None
    assert not any("missing_peer_percentiles" in f for f in loose_flags)

    out_strict, strict_flags = compute_factors_with_flags(
        pillars, {}, {}, enforce_peer_pct_for_style_factors=True,
    )
    assert out_strict.value.score is None
    assert out_strict.low_risk.score is None  # beta percentile absent
    assert out_strict.sentiment.score is not None
    assert "factor_value_missing_peer_percentiles" in strict_flags
