"""Deterministic factor formulas mapping pillar scores (1-5) + peer percentiles (0-1)
to 6 factor scores (0-100).

Each factor returns its `inputs` audit dict so the score is reproducible and reviewable.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from api.dimensions.schemas import (
    FactorScore, FactorScores, PillarScores,
)


INVERTED_PEER_FIELDS = {"pe_ttm", "pb", "ev_ebitda", "ps_ttm", "peg", "beta"}


def scale_1_5_to_0_100(score: int) -> float:
    return (score - 1) * 25.0


def _weighted(components: List[Tuple[str, Optional[float], float]]) -> Tuple[
    Optional[float], Dict[str, float]
]:
    """Each component is (name, value_0_to_100_or_None, weight)."""
    active = [(n, v, w) for (n, v, w) in components if v is not None]
    if not active:
        return None, {}
    total_w = sum(w for (_, _, w) in active)
    if total_w == 0:
        return None, {}
    score = sum(v * (w / total_w) for (_, v, w) in active)
    return score, {f"weight_{n}": w / total_w for (n, _, w) in active}


def _pct_to_100(pct: Optional[float]) -> Optional[float]:
    return pct * 100.0 if pct is not None else None


def _inv_score(pillar_score: int) -> float:
    """Inverted pillar (higher score = lower risk) → low-risk contribution."""
    return scale_1_5_to_0_100(pillar_score)


def compute_factors_sentiment_only(
    pillars: PillarScores,
) -> Tuple[FactorScores, List[str]]:
    """Factors 0–100 with only the sentiment-related blend; other factors are blank.

    Used when peer percentiles are unavailable so value/growth/quality/momentum/low_risk are
    not synthesized from pillars alone (misleading vs peers).
    """
    blank = FactorScore(score=None, inputs={})
    sentiment_score, sentiment_inputs = _weighted([
        ("retail_sentiment_pillar",
         scale_1_5_to_0_100(pillars.sentiment.retail_sentiment.score), 0.25),
        ("social_buzz_pillar",
         scale_1_5_to_0_100(pillars.sentiment.social_buzz.score), 0.20),
        ("consensus_pillar",
         scale_1_5_to_0_100(pillars.sentiment.consensus_quality.score), 0.20),
        ("narrative_pillar",
         scale_1_5_to_0_100(pillars.sentiment.narrative_strength.score), 0.15),
        ("catalyst_pillar",
         scale_1_5_to_0_100(pillars.news.catalyst_strength.score), 0.20),
    ])
    flags = [
        "factor_value_missing_peer_percentiles",
        "factor_growth_missing_peer_percentiles",
        "factor_quality_missing_peer_percentiles",
        "factor_momentum_missing_peer_percentiles",
        "factor_low_risk_missing_peer_percentiles",
    ]
    if sentiment_score is None:
        flags.append("factor_sentiment_no_inputs")
    return (
        FactorScores(
            value=blank,
            growth=blank,
            quality=blank,
            momentum=blank,
            low_risk=blank,
            sentiment=FactorScore(score=sentiment_score, inputs=sentiment_inputs),
        ),
        flags,
    )


def compute_factors(
    pillars: PillarScores,
    facts: Dict[str, Optional[float]],
    peer_pct: Dict[str, Optional[float]],
) -> FactorScores:
    """Public alias — returns FactorScores only (no flags)."""
    factors, _ = compute_factors_with_flags(pillars, facts, peer_pct)
    return factors


def compute_factors_with_flags(
    pillars: PillarScores,
    facts: Dict[str, Optional[float]],
    peer_pct: Dict[str, Optional[float]],
    *,
    enforce_peer_pct_for_style_factors: bool = False,
) -> Tuple[FactorScores, List[str]]:
    flags: List[str] = []

    value_score, value_inputs = _weighted([
        ("valuation_pillar", scale_1_5_to_0_100(pillars.fundamentals.valuation.score), 0.5),
        ("pe_pct", _pct_to_100(peer_pct.get("pe_ttm")), 0.3),
        ("pb_pct", _pct_to_100(peer_pct.get("pb")), 0.2),
    ])
    if enforce_peer_pct_for_style_factors and (
        peer_pct.get("pe_ttm") is None and peer_pct.get("pb") is None
    ):
        value_score = None
        value_inputs = {}
        flags.append("factor_value_missing_peer_percentiles")

    growth_score, growth_inputs = _weighted([
        ("growth_pillar", scale_1_5_to_0_100(pillars.fundamentals.growth.score), 0.5),
        ("eps_growth_pct", _pct_to_100(peer_pct.get("eps_growth_yoy")), 0.25),
        ("revenue_growth_pct", _pct_to_100(peer_pct.get("revenue_growth_yoy")), 0.25),
    ])
    if enforce_peer_pct_for_style_factors and (
        peer_pct.get("eps_growth_yoy") is None and peer_pct.get("revenue_growth_yoy") is None
    ):
        growth_score = None
        growth_inputs = {}
        flags.append("factor_growth_missing_peer_percentiles")

    quality_score, quality_inputs = _weighted([
        ("profitability_pillar",
         scale_1_5_to_0_100(pillars.fundamentals.profitability.score), 0.35),
        ("balance_sheet_pillar",
         scale_1_5_to_0_100(pillars.fundamentals.balance_sheet_strength.score), 0.25),
        ("roe_pct", _pct_to_100(peer_pct.get("roe")), 0.25),
        ("interest_coverage_pct", _pct_to_100(peer_pct.get("interest_coverage")), 0.15),
    ])
    if enforce_peer_pct_for_style_factors and (
        peer_pct.get("roe") is None and peer_pct.get("interest_coverage") is None
    ):
        quality_score = None
        quality_inputs = {}
        flags.append("factor_quality_missing_peer_percentiles")

    momentum_score, momentum_inputs = _weighted([
        ("trend_pillar", scale_1_5_to_0_100(pillars.market.trend.score), 0.30),
        ("momentum_pillar", scale_1_5_to_0_100(pillars.market.momentum.score), 0.30),
        ("return_3m_pct", _pct_to_100(peer_pct.get("return_3m")), 0.20),
        ("return_12m_pct", _pct_to_100(peer_pct.get("return_12m")), 0.20),
    ])
    if enforce_peer_pct_for_style_factors and (
        peer_pct.get("return_3m") is None and peer_pct.get("return_12m") is None
    ):
        momentum_score = None
        momentum_inputs = {}
        flags.append("factor_momentum_missing_peer_percentiles")

    low_risk_score, low_risk_inputs = _weighted([
        ("volatility_risk_pillar", _inv_score(pillars.market.volatility_risk.score), 0.40),
        ("surprise_risk_pillar", _inv_score(pillars.news.surprise_risk.score), 0.30),
        ("beta_pct", _pct_to_100(peer_pct.get("beta")), 0.30),
    ])
    if enforce_peer_pct_for_style_factors and peer_pct.get("beta") is None:
        low_risk_score = None
        low_risk_inputs = {}
        flags.append("factor_low_risk_missing_peer_percentiles")

    sentiment_score, sentiment_inputs = _weighted([
        ("retail_sentiment_pillar",
         scale_1_5_to_0_100(pillars.sentiment.retail_sentiment.score), 0.25),
        ("social_buzz_pillar",
         scale_1_5_to_0_100(pillars.sentiment.social_buzz.score), 0.20),
        ("consensus_pillar",
         scale_1_5_to_0_100(pillars.sentiment.consensus_quality.score), 0.20),
        ("narrative_pillar",
         scale_1_5_to_0_100(pillars.sentiment.narrative_strength.score), 0.15),
        ("catalyst_pillar",
         scale_1_5_to_0_100(pillars.news.catalyst_strength.score), 0.20),
    ])

    for name, score in [
        ("value", value_score), ("growth", growth_score), ("quality", quality_score),
        ("momentum", momentum_score), ("low_risk", low_risk_score),
        ("sentiment", sentiment_score),
    ]:
        if score is None:
            peer_miss = f"factor_{name}_missing_peer_percentiles"
            if peer_miss in flags:
                continue
            flags.append(f"factor_{name}_no_inputs")

    return (
        FactorScores(
            value=FactorScore(score=value_score, inputs=value_inputs),
            growth=FactorScore(score=growth_score, inputs=growth_inputs),
            quality=FactorScore(score=quality_score, inputs=quality_inputs),
            momentum=FactorScore(score=momentum_score, inputs=momentum_inputs),
            low_risk=FactorScore(score=low_risk_score, inputs=low_risk_inputs),
            sentiment=FactorScore(score=sentiment_score, inputs=sentiment_inputs),
        ),
        flags,
    )
