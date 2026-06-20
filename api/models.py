"""Pydantic models for the TradingAgents API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

from api.dimensions.schemas import (
    DimensionsCommentary,
    FactSnapshot,
    FactorScore,
    FactorScores,
    PillarScore,
    PillarScores,
    StockDimensions,
)

AnalystId = Literal[
    "market",
    "social",
    "news",
    "fundamentals",
    "hot_money",
    "policy",
    "lockup",
    "kronos",
    "alt_data",
]
DEFAULT_ANALYST_ORDER: tuple[AnalystId, ...] = (
    "market",
    "social",
    "news",
    "fundamentals",
    "hot_money",
    "policy",
    "lockup",
    "kronos",
)
SCAN_MODE_ANALYSTS: tuple[AnalystId, ...] = (
    "market",
    "news",
    "fundamentals",
    "kronos",
)
VALID_ANALYST_IDS: frozenset[str] = frozenset([*DEFAULT_ANALYST_ORDER, "alt_data"])


def _validate_analyst_list_members(v: Optional[List[str]]) -> Optional[List[str]]:
    """Reject unknown analyst ids (validated after normalization)."""
    if not v:
        return None
    unknown = sorted({x for x in v if x not in VALID_ANALYST_IDS})
    if unknown:
        allowed = ", ".join(repr(x) for x in sorted(VALID_ANALYST_IDS))
        raise ValueError(f"Unknown analyst id(s): {unknown}. Allowed: {allowed}")
    return v


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
        description="Analysts to run (order preserved). Defaults to all configured analysts.",
    )
    mode: Literal["scan", "full"] = Field(
        default="full",
        description="scan = lightweight preset (4 analysts, 1 debate round). full = default pipeline.",
    )
    overnight_signal: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional precomputed overnight signal dict to seed graph state.",
    )

    @field_validator("analysts", mode="before")
    @classmethod
    def _normalize_analysts(
        cls, v: Optional[Union[List[str], str]]
    ) -> Optional[List[str]]:
        if v is None:
            return None
        if isinstance(v, str):
            v = [v]
        out: List[str] = []
        for item in v:
            if not isinstance(item, str):
                continue
            out.append(item.strip().lower())
        return out or None

    @field_validator("analysts", mode="after")
    @classmethod
    def _analysts_must_be_registered(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        return _validate_analyst_list_members(v)


class AnalysisResult(BaseModel):
    """Payload returned when a job completes."""

    ticker: str
    date: str
    rating: str = Field(..., description="Extracted 5-tier rating: Buy / Overweight / Hold / Underweight / Sell")
    confidence: Optional[float] = Field(
        default=None,
        description="Heuristic confidence 0–1 derived from rating tier for batch summaries.",
    )
    reports: Dict[str, str] = Field(default_factory=dict, description="Section name → markdown content")
    analyst_coverage: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None,
        description="Per analyst id: ok vs empty and diagnostics (present when the job ran with explicit analyst selection).",
    )
    structured: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Raw structured fields from ResearchPlan / TraderDecision / PortfolioDecision if available.",
    )
    artifacts_path: Optional[str] = Field(
        default=None,
        description="Local filesystem path to the saved markdown report directory.",
    )
    completed_at: Union[datetime, str]
    dimensions: Optional[StockDimensions] = None
    dimensions_commentary: Optional[DimensionsCommentary] = None
    dimensions_error: Optional[str] = None
    dimensions_in_graph: Optional[bool] = Field(
        default=None,
        description="True when LangGraph serialized a dimensions snapshot before the PM step.",
    )
    confidence_raw_tier: Optional[float] = Field(
        default=None,
        description="Pre-calibration confidence from rating tier alone (0..1).",
    )
    confidence_breakdown: Optional[Dict[str, float]] = Field(
        default=None,
        description="Calibration breakdown: tier, coherence_penalty, data_quality_penalty, peer_penalty.",
    )
    confidence_inputs: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Inputs that fed calibration: supporting/conflicting factors, weak_data, peer_scope.",
    )
    live_context_at_run: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Live quote and plan comparison captured when the graph started.",
    )
    plan_levels: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Derived entry/stop/target levels from analyst reports and structured payload.",
    )
    options_recommendation: Optional[str] = Field(
        default=None,
        description="Options strategy recommendation markdown when options_strategist_enabled=True.",
    )
    options_chain_snapshot: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Nearest-expiration options chain data used by the strategist.",
    )


class AnalyzeResponse(BaseModel):
    """POST /analyze immediate response."""

    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime


class JobDimensionsResponse(BaseModel):
    """GET /jobs/{job_id}/dimensions — snapshot from the completed job result."""

    dimensions: Optional[StockDimensions] = None
    commentary: Optional[DimensionsCommentary] = None
    error: Optional[str] = Field(
        default=None,
        description="Populated when the dimensions post-pass failed but the job still completed.",
    )


class LiveQuoteSnapshot(BaseModel):
    ticker: str
    price: Optional[float] = None
    currency: Optional[str] = None
    fetched_at: str
    source: str = "yfinance_regularMarketPrice"
    error: Optional[str] = None


class PlanLevelsSnapshot(BaseModel):
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    price_target: Optional[float] = None


class PlanComparisonSnapshot(BaseModel):
    status: str
    guidance: str
    live_price: Optional[float] = None
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    price_target: Optional[float] = None
    delta_vs_entry_pct: Optional[float] = None
    delta_vs_stop_pct: Optional[float] = None
    delta_vs_target_pct: Optional[float] = None
    run_time_price: Optional[float] = None
    suggest_refresh: Optional[bool] = None


class JobLiveContextResponse(BaseModel):
    """GET /jobs/{job_id}/live-context — live quote vs persisted plan levels."""

    quote: LiveQuoteSnapshot
    report_close: Optional[float] = None
    trade_date: Optional[str] = None
    levels: PlanLevelsSnapshot
    comparison: PlanComparisonSnapshot
    run_time_quote: Optional[LiveQuoteSnapshot] = None
    levels_anchored_at_run: Optional[bool] = Field(
        default=None,
        description="False when entry was >5% above the live quote captured at run start.",
    )
    historical_rating_note: str = (
        "Rating and levels below are from the completed run; live guidance reflects "
        "current market price."
    )


class JobStatusResponse(AnalyzeResponse):
    """GET /jobs/{job_id} polled response."""

    ticker: Optional[str] = None
    date: Optional[str] = None
    result: Optional[AnalysisResult] = None
    error: Optional[str] = None
    progress_events: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Structured log lines for UI terminal view.",
    )
    batch_id: Optional[str] = None
    resumable: bool = Field(
        default=False,
        description="True when a LangGraph checkpoint exists and the job can be resumed.",
    )
    last_graph_step: Optional[int] = Field(
        default=None,
        description="Latest LangGraph checkpoint step when resumable.",
    )
    checkpoint_thread_id: Optional[str] = Field(
        default=None,
        description="LangGraph thread id (ticker+date hash) used for checkpoint resume.",
    )
    provenance: Optional[RunProvenance] = Field(
        default=None,
        description="LLM and data-source snapshot for this job (live + completed).",
    )
    trigger: Optional[str] = Field(
        default=None,
        description="Job origin, e.g. overnight_monitor or scan.",
    )
    signal_score: Optional[int] = Field(
        default=None,
        description="Overnight signal score when triggered by monitor.",
    )
    analysts: List[str] = Field(
        default_factory=list,
        description="Analyst ids selected for this job (for re-run from History).",
    )


class ResumeJobResponse(BaseModel):
    """POST /jobs/{job_id}/resume immediate response."""

    job_id: str
    status: Literal["queued", "running"]
    resumable: bool = True
    last_graph_step: Optional[int] = None
    message: str = Field(default="Resume queued.")


class MonitorWatchlistSetRequest(BaseModel):
    tickers: List[str] = Field(default_factory=list)


class MonitorTickerRequest(BaseModel):
    ticker: str = Field(..., min_length=1)


class BatchAnalyzeRequest(BaseModel):
    """POST /batches — analyze many tickers with shared settings."""

    tickers: List[str] = Field(..., min_length=1, max_length=100)
    date: Optional[str] = Field(
        None,
        description="Analysis date YYYY-MM-DD; defaults to today.",
    )
    config_overrides: Optional[Dict[str, Any]] = Field(default_factory=dict)
    analysts: Optional[List[str]] = Field(default=None)
    report_format: Optional[Literal["markdown", "json", "structured"]] = Field(
        default=None,
        description="Output format for the report artifact. Inherits single-analyze default when omitted.",
    )

    @field_validator("tickers", mode="before")
    @classmethod
    def _split_tickers(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            parts = [p.strip() for p in v.replace("\n", ",").split(",")]
            return [p for p in parts if p]
        return v

    @field_validator("analysts", mode="before")
    @classmethod
    def _normalize_batch_analysts(
        cls, v: Optional[Union[List[str], str]]
    ) -> Optional[List[str]]:
        if v is None:
            return None
        if isinstance(v, str):
            v = [v]
        out: List[str] = []
        for item in v:
            if not isinstance(item, str):
                continue
            out.append(item.strip().lower())
        return out or None

    @field_validator("analysts", mode="after")
    @classmethod
    def _batch_analysts_must_be_registered(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        return _validate_analyst_list_members(v)


class BatchAnalyzeResponse(BaseModel):
    batch_id: str
    job_ids: List[str]
    status: str = "queued"
    created_at: datetime


class BatchStatusResponse(BaseModel):
    batch_id: str
    jobs: List[JobStatusResponse]
    summary: Dict[str, int] = Field(
        default_factory=dict,
        description="Counts by status, e.g. queued/running/completed/failed.",
    )


NewsSourceId = Literal[
    "yfinance",
    "yfinance_macro",
    "finnhub",
    "google_rss",
    "akshare",
    "reddit",
    "stocktwits",
    "alpha_vantage",
]


class NewsItem(BaseModel):
    title: str
    summary: str = ""
    publisher: str = ""
    link: str = ""
    pub_date: Optional[str] = None
    ticker: str
    sentiment: Literal["bullish", "bearish", "neutral"] = "neutral"
    sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    sector_tags: List[str] = Field(default_factory=list)
    # Required (no default): FastAPI JSON encoding uses exclude_defaults=True and would
    # omit ``source`` when it equals ``"yfinance"``, breaking client-side source counts.
    source: NewsSourceId


class NewsFeedResponse(BaseModel):
    ticker: str
    items: List[NewsItem]
    fetched_at: datetime
    """Per-source fetch errors (e.g. rate limit); omitted keys mean success."""
    source_errors: Dict[str, str] = Field(default_factory=dict)


class RuntimeConfigUpdateRequest(BaseModel):
    """Non-secret service fields merged into running config and persisted."""

    service_overrides: Optional[Dict[str, Any]] = None
    """Optional env keys to persist (must be in allow-list)."""

    secrets: Optional[Dict[str, str]] = None


class DataSourceCheck(BaseModel):
    """Best-effort health probe status for a single data source/vendor."""

    ok: bool
    configured: bool
    checked_at: str
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    ok: bool
    llm_provider: str
    api_key_configured: bool
    state_store: str
    cloudflare_kv_configured: bool
    cloudflare_d1_configured: bool = False
    data_cache_dir: str
    results_dir: str
    yfinance_reachable: Optional[bool] = None
    data_source_checks: Dict[str, DataSourceCheck] = Field(default_factory=dict)
    supported_analyst_ids: List[str] = Field(
        default_factory=lambda: list(DEFAULT_ANALYST_ORDER),
        description="Analyst keys accepted by POST /analyze and POST /batches.",
    )
    notifications: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Notification layer status snapshot.",
    )


class RunProvenance(BaseModel):
    """LLM, data routing, and analyst coverage summary for bias-aware comparison."""

    llm_provider: Optional[str] = None
    llm_deep: Optional[str] = None
    llm_quick: Optional[str] = None
    data_routing: Optional[str] = Field(
        default=None,
        description="Short vendor routing label (OHLCV, fundamentals, news, etc.).",
    )
    analysts_selected: List[str] = Field(default_factory=list)
    analysts_ok: int = 0
    analysts_empty: int = 0
    analysts_failed: int = 0
    analysts_total: int = 0
    source_pillars: int = Field(
        0,
        ge=0,
        le=4,
        description="How many of the four data-vendor pillars were configured.",
    )
    vendor_count: int = Field(
        0,
        ge=0,
        description="Distinct primary vendors across pillars (1 = single-source risk).",
    )
    bias_warnings: List[str] = Field(
        default_factory=list,
        description="Human-readable flags when setup may skew comparisons.",
    )


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
    facts_sector: Optional[str] = Field(
        default=None,
        description="From dimensions snapshot facts (when list comes from D1).",
    )
    facts_industry: Optional[str] = Field(default=None)
    has_dimensions: Optional[bool] = Field(
        default=None,
        description="True when persisted row includes a non-empty dimensions JSON.",
    )
    has_commentary: Optional[bool] = Field(
        default=None,
        description="True when persisted row includes commentary JSON.",
    )
    provenance: Optional[RunProvenance] = Field(
        default=None,
        description="LLM + data sources + analyst coverage snapshot for this run.",
    )


class HistoryCoverageRow(BaseModel):
    """Aggregated persisted-run counts by sector/industry (D1 history only)."""

    sector: str
    industry: str
    run_count: int = Field(..., ge=0)
    with_dimensions_count: int = Field(..., ge=0)
    with_commentary_count: int = Field(..., ge=0)
    latest_completed_at: Optional[str] = None


class IndustryConstituentRow(BaseModel):
    """Catalog constituent ticker with optional latest persisted analysis coverage."""

    ticker: str
    market: str = Field(description="US or HK from cold-start catalog.")
    run_count: int = Field(0, ge=0)
    has_report: bool = False
    has_dimensions: bool = False
    has_commentary: bool = False
    latest_rating: Optional[str] = None
    latest_date: Optional[str] = None
    latest_run_id: Optional[str] = None
    latest_completed_at: Optional[str] = None


class CatalogStatusResponse(BaseModel):
    """Yahoo sector/industry catalog freshness — row counts and most-recent refresh time."""

    d1_enabled: bool
    buckets: int = Field(0, ge=0)
    constituents_total: int = Field(0, ge=0)
    constituents_us: int = Field(0, ge=0)
    constituents_hk: int = Field(0, ge=0)
    latest_bucket_refreshed_at: Optional[float] = Field(
        None, description="POSIX timestamp of newest yahoo_sector_industry_buckets.updated_at."
    )
    latest_constituent_refreshed_at: Optional[float] = Field(
        None, description="POSIX timestamp of newest yahoo_industry_constituents.updated_at."
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
    analyst_coverage: Optional[Dict[str, Dict[str, Any]]] = None
    structured: Optional[Dict[str, Any]] = None
    artifacts_path: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    batch_id: Optional[str] = None
    config_snapshot: Dict[str, Any] = Field(default_factory=dict)
    provenance: Optional[RunProvenance] = None
    dimensions: Optional[StockDimensions] = None
    dimensions_commentary: Optional[DimensionsCommentary] = None
    dimensions_error: Optional[str] = None
    dimensions_in_graph: Optional[bool] = None
    plan_levels: Optional[Dict[str, Any]] = None
    live_context_at_run: Optional[Dict[str, Any]] = None
    options_recommendation: Optional[str] = None
    options_chain_snapshot: Optional[Dict[str, Any]] = None


class HistoryCompareRequest(BaseModel):
    run_id_a: str = Field(..., min_length=1)
    run_id_b: str = Field(..., min_length=1)


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


class HistoryCompareResponse(BaseModel):
    a: HistoryCompareSide
    b: HistoryCompareSide


class RatingDistributionBucket(BaseModel):
    rating: Literal["Buy", "Overweight", "Hold", "Underweight", "Sell"]
    count: int = Field(ge=0)
    pct: float = Field(ge=0, le=100)


class FactorAggregate(BaseModel):
    factor: Literal["value", "growth", "quality", "momentum", "low_risk", "sentiment"]
    median: float = Field(ge=0, le=100)
    tickers_with_data: int = Field(ge=0)


class CoverageQualitySummary(BaseModel):
    analyzed_tickers: int = Field(ge=0)
    total_constituents: int = Field(ge=0)
    pct_with_dimensions: float = Field(ge=0, le=100)
    pct_with_commentary: float = Field(ge=0, le=100)
    freshness_days_median: Optional[float] = Field(default=None, ge=0)
    freshness_days_p90: Optional[float] = Field(default=None, ge=0)
    latest_run_link: Optional[str] = None


class SectorAnalyticsResponse(BaseModel):
    sector: str
    industry: str
    market: Literal["ALL", "US", "HK"]
    health_score: float = Field(ge=0, le=100)
    rating_distribution: List[RatingDistributionBucket]
    factor_medians: List[FactorAggregate]
    coverage_quality: CoverageQualitySummary
    avg_confidence: float = Field(ge=0, le=100)
    rating_score: float = Field(ge=0, le=100)
    factor_score: float = Field(ge=0, le=100)
    freshness_score: float = Field(ge=0, le=100)
    generated_at: str


class HistoryBulkDeleteRequest(BaseModel):
    run_ids: List[str] = Field(..., min_length=1, max_length=500)


class HistoryDeleteAllRequest(BaseModel):
    confirm: bool = Field(
        ...,
        description="Must be true to confirm deleting all runs matching optional filters.",
    )
    ticker: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None


class HistoryBulkDeleteResponse(BaseModel):
    deleted_count: int
    deleted_run_ids: List[str] = Field(default_factory=list)
    missing_run_ids: List[str] = Field(default_factory=list)
    scope: str = "selected"


from api.notifications_models import (
    NotificationChannel,
    NotificationConfig,
    NotificationSendRequest,
    NotificationStatus,
    NotificationTestRequest,
)

__all__ = [
    *globals().get("__all__", []),
    "DimensionsCommentary",
    "FactSnapshot",
    "FactorScore",
    "FactorScores",
    "PillarScore",
    "PillarScores",
    "StockDimensions",
    "HistoryCoverageRow",
    "IndustryConstituentRow",
    "RatingDistributionBucket",
    "FactorAggregate",
    "CoverageQualitySummary",
    "SectorAnalyticsResponse",
    "NotificationChannel",
    "NotificationConfig",
    "NotificationSendRequest",
    "NotificationStatus",
    "NotificationTestRequest",
]

