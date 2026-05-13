"""Pydantic models for the TradingAgents API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from api.dimensions.schemas import (
    DimensionsCommentary,
    FactSnapshot,
    FactorScore,
    FactorScores,
    PillarScore,
    PillarScores,
    StockDimensions,
)


class AnalyzeRequest(BaseModel):
    """POST /analyze request body."""

    ticker: str = Field(..., description="Ticker symbol, e.g. AAPL or 0700.HK")
    date: Optional[str] = Field(
        None,
        description="Analysis date (YYYY-MM-DD). Defaults to today.",
    )
    config_overrides: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Optional config keys to override service defaults (e.g. max_debate_rounds).",
    )
    report_format: Literal["markdown", "json", "structured"] = Field(
        default="markdown",
        description="Output format for the report artifact.",
    )
    analysts: Optional[List[str]] = Field(
        default=None,
        description="List of analysts to run: market, social, news, fundamentals. Defaults to all.",
    )


class AnalysisResult(BaseModel):
    """Payload returned when a job completes."""

    ticker: str
    date: str
    rating: str = Field(..., description="Extracted 5-tier rating: Buy / Overweight / Hold / Underweight / Sell")
    reports: Dict[str, str] = Field(default_factory=dict, description="Section name → markdown content")
    structured: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Raw structured fields from ResearchPlan / TraderDecision / PortfolioDecision if available.",
    )
    artifacts_path: Optional[str] = Field(
        default=None,
        description="Local filesystem path to the saved markdown report directory.",
    )
    completed_at: datetime
    dimensions: Optional[StockDimensions] = None
    dimensions_commentary: Optional[DimensionsCommentary] = None
    dimensions_error: Optional[str] = None


class AnalyzeResponse(BaseModel):
    """POST /analyze immediate response."""

    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime


class JobStatusResponse(AnalyzeResponse):
    """GET /jobs/{job_id} polled response."""

    result: Optional[AnalysisResult] = None
    error: Optional[str] = None


class HistoryRunRef(BaseModel):
    """Compact row for history lists (from KV indexes)."""

    run_id: str
    job_id: Optional[str] = None
    ticker: Optional[str] = None
    date: Optional[str] = None
    rating: Optional[str] = None
    confidence: Optional[float] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    batch_id: Optional[str] = None
    factor_scores: Optional[Dict[str, float]] = Field(
        default=None,
        description="Compact 6-factor summary for list views (value/growth/quality/momentum/low_risk/sentiment).",
    )


class HistoryRunDetail(BaseModel):
    """Full persisted run (same shape as completed job result + metadata)."""

    run_id: str
    job_id: str
    ticker: str
    date: str
    rating: str
    confidence: Optional[float] = None
    reports: Dict[str, str] = Field(default_factory=dict)
    structured: Optional[Dict[str, Any]] = None
    artifacts_path: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    batch_id: Optional[str] = None
    config_snapshot: Dict[str, Any] = Field(default_factory=dict)
    dimensions: Optional[StockDimensions] = None
    dimensions_commentary: Optional[DimensionsCommentary] = None
    dimensions_error: Optional[str] = None


class HistoryCompareSide(BaseModel):
    run_id: Optional[str] = None
    job_id: Optional[str] = None
    ticker: Optional[str] = None
    date: Optional[str] = None
    rating: Optional[str] = None
    confidence: Optional[float] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    config_snapshot: Dict[str, Any] = Field(default_factory=dict)
    reports: Dict[str, str] = Field(default_factory=dict)
    structured: Optional[Dict[str, Any]] = None
    artifacts_path: Optional[str] = None
    excerpt_portfolio_decision: str = ""
    excerpt_trader_plan: str = ""
    dimensions: Optional[StockDimensions] = None
    dimensions_commentary: Optional[DimensionsCommentary] = None


__all__ = [
    *globals().get("__all__", []),
    "DimensionsCommentary",
    "FactSnapshot",
    "FactorScore",
    "FactorScores",
    "PillarScore",
    "PillarScores",
    "StockDimensions",
]
