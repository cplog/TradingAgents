"""Pydantic schemas for the standardized stock dimensions layer."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class FactSnapshot(BaseModel):
    """Deterministic yfinance-sourced facts for a (ticker, as_of_date)."""

    as_of_date: str
    currency: str
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap_usd: Optional[float] = None

    price: Optional[float] = None
    price_52w_high: Optional[float] = None
    pct_off_52w_high: Optional[float] = None
    return_1m: Optional[float] = None
    return_3m: Optional[float] = None
    return_6m: Optional[float] = None
    return_12m: Optional[float] = None
    beta: Optional[float] = None

    realized_vol_30d: Optional[float] = None
    rsi_14: Optional[float] = None
    avg_daily_dollar_volume_30d: Optional[float] = None

    pe_ttm: Optional[float] = None
    forward_pe: Optional[float] = None
    peg: Optional[float] = None
    ev_ebitda: Optional[float] = None
    ps_ttm: Optional[float] = None
    pb: Optional[float] = None
    fcf_yield: Optional[float] = None

    revenue_growth_yoy: Optional[float] = None
    eps_growth_yoy: Optional[float] = None
    revenue_cagr_3y: Optional[float] = None
    eps_cagr_3y: Optional[float] = None

    roe: Optional[float] = None
    roic: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    debt_to_equity: Optional[float] = None
    interest_coverage: Optional[float] = None
    current_ratio: Optional[float] = None

    dividend_yield: Optional[float] = None
    payout_ratio: Optional[float] = None

    analyst_count: Optional[int] = None
    analyst_target_mean: Optional[float] = None
    analyst_recommendation_mean: Optional[float] = None


class PillarScore(BaseModel):
    score: int = Field(..., ge=1, le=5)
    rationale: str


class MarketPillar(BaseModel):
    trend: PillarScore
    momentum: PillarScore
    volatility_risk: PillarScore = Field(
        ..., description="Lower score = MORE volatility risk; higher score = lower risk."
    )
    setup_quality: PillarScore


class SentimentPillar(BaseModel):
    retail_sentiment: PillarScore
    social_buzz: PillarScore
    consensus_quality: PillarScore
    narrative_strength: PillarScore


class NewsPillar(BaseModel):
    catalyst_strength: PillarScore
    macro_alignment: PillarScore
    headline_quality: PillarScore
    surprise_risk: PillarScore = Field(
        ..., description="Lower score = MORE surprise risk; higher score = lower risk."
    )


class FundamentalsPillar(BaseModel):
    valuation: PillarScore
    growth: PillarScore
    profitability: PillarScore
    balance_sheet_strength: PillarScore


class PillarScores(BaseModel):
    market: MarketPillar
    sentiment: SentimentPillar
    news: NewsPillar
    fundamentals: FundamentalsPillar


class FactorScore(BaseModel):
    score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    inputs: Dict[str, float] = Field(default_factory=dict)


class FactorScores(BaseModel):
    value: FactorScore
    growth: FactorScore
    quality: FactorScore
    momentum: FactorScore
    low_risk: FactorScore
    sentiment: FactorScore


class StockDimensions(BaseModel):
    ticker: str
    as_of_date: str
    facts: FactSnapshot
    pillar_scores: PillarScores
    factor_scores: FactorScores
    dimensions_version: str
    peer_universe_id: Optional[str] = None
    data_quality_flags: List[str] = Field(default_factory=list)
    source: Literal["full_run", "facts_only"] = "full_run"


class DimensionsCommentary(BaseModel):
    alignment: Literal["aligned", "partial", "misaligned"]
    supporting_dimensions: List[str]
    conflicting_dimensions: List[str]
    risk_flags: List[str]
    summary: str
