"""Pydantic models for Hot Ideas (Topics) feature."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class TopicCadence(str, Enum):
    daily = "daily"
    weekly = "weekly"
    manual = "manual"


class TopicSource(str, Enum):
    seed = "seed"
    user = "user"


class TickerMarket(str, Enum):
    us = "us"
    hk = "hk"
    cn = "cn"
    other = "other"


class TickerCandidate(BaseModel):
    ticker: str
    company_name: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: Optional[str] = None
    market: TickerMarket = TickerMarket.us


class TopicArticle(BaseModel):
    title: str
    url: str
    snippet: Optional[str] = None
    published_at: Optional[str] = None
    source: Optional[str] = None


class TopicRunStatus(str, Enum):
    running = "running"
    completed = "completed"
    failed = "failed"


class TopicRun(BaseModel):
    run_id: str
    topic_id: str
    started_at: str
    completed_at: Optional[str] = None
    status: TopicRunStatus
    articles: List[TopicArticle] = Field(default_factory=list)
    candidates: List[TickerCandidate] = Field(default_factory=list)
    theme_summary: Optional[str] = None
    error: Optional[str] = None


class Topic(BaseModel):
    id: str
    label: str
    query: str
    cadence: TopicCadence = TopicCadence.daily
    pinned: bool = False
    source: TopicSource = TopicSource.user
    created_at: str
    updated_at: str
    last_run_at: Optional[str] = None
    last_refresh_at: Optional[str] = None


class TopicSummary(BaseModel):
    id: str
    label: str
    query: str
    cadence: TopicCadence
    pinned: bool
    source: TopicSource
    last_run_at: Optional[str] = None
    candidate_count: int = 0
    top_candidates: List[TickerCandidate] = Field(default_factory=list)


class TopicDetailResponse(BaseModel):
    topic: Topic
    latest_run: Optional[TopicRun] = None


class TopicSearchRequest(BaseModel):
    query: str
    label: Optional[str] = None
    cadence: TopicCadence = TopicCadence.daily


class TopicUpdateRequest(BaseModel):
    label: Optional[str] = None
    query: Optional[str] = None
    cadence: Optional[TopicCadence] = None


class TopicListResponse(BaseModel):
    topics: List[TopicSummary]


class TopicRunsResponse(BaseModel):
    runs: List[TopicRun]


class TopicRefreshResponse(BaseModel):
    run: TopicRun


class ExtractionResult(BaseModel):
    """Structured LLM output for ticker extraction."""

    theme_summary: str
    candidates: List[TickerCandidate] = Field(default_factory=list)
