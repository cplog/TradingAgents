"""Pydantic models for the TradingAgents API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


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


class AnalyzeResponse(BaseModel):
    """POST /analyze immediate response."""

    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime


class JobStatusResponse(AnalyzeResponse):
    """GET /jobs/{job_id} polled response."""

    result: Optional[AnalysisResult] = None
    error: Optional[str] = None
