"""Orchestrator: facts → peers → pillars → factors → StockDimensions."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from api.dimensions.commentary import CommentaryError, build_commentary as _bc
from api.dimensions.facts import FactExtractionError, extract_facts
from api.dimensions.factors import (
    INVERTED_PEER_FIELDS, compute_factors_with_flags,
)
from api.dimensions.peers import (
    PeerCache, build_peer_pct_table, peer_universe_id, slug_for_sector,
)
from api.dimensions.schemas import (
    DimensionsCommentary, FactSnapshot, FundamentalsPillar, MarketPillar,
    NewsPillar, PillarScore, PillarScores, SentimentPillar, StockDimensions,
)
from api.dimensions.scoring import PillarScoringError, score_pillars
from api.dimensions.version import DIMENSIONS_VERSION

logger = logging.getLogger(__name__)


class DimensionsBuildError(RuntimeError):
    pass


def _get_peer_cache_dir(config: Optional[Dict[str, Any]]) -> Path:
    cfg = config or {}
    base = Path(cfg.get("data_cache_dir") or "./data_cache")
    return base / "peer_facts"


def _load_or_refresh_peers(
    sector: Optional[str], industry: Optional[str], cache_dir: Path,
    ttl_hours: int = 24,
) -> Tuple[List[str], Dict[str, Dict[str, Optional[float]]]]:
    """v1: returns whatever is cached. Refresh is a separate operation
    (scripts/warm_peer_cache.py or admin endpoint). Missing cache → empty."""
    slug = slug_for_sector(sector, industry)
    if not slug:
        return [], {}
    cache = PeerCache(base_dir=cache_dir)
    rec = cache.read(slug)
    if rec is None:
        return [], {}
    return rec.tickers, rec.facts


def _facts_to_peer_dict(facts: FactSnapshot) -> Dict[str, Optional[float]]:
    """Subset of facts used for peer percentile ranking."""
    return {
        "pe_ttm": facts.pe_ttm,
        "forward_pe": facts.forward_pe,
        "peg": facts.peg,
        "ev_ebitda": facts.ev_ebitda,
        "ps_ttm": facts.ps_ttm,
        "pb": facts.pb,
        "eps_growth_yoy": facts.eps_growth_yoy,
        "revenue_growth_yoy": facts.revenue_growth_yoy,
        "roe": facts.roe,
        "interest_coverage": facts.interest_coverage,
        "return_3m": facts.return_3m,
        "return_12m": facts.return_12m,
        "beta": facts.beta,
    }


def _neutral_pillars() -> PillarScores:
    def n(): return PillarScore(score=3, rationale="neutral default (facts-only)")
    return PillarScores(
        market=MarketPillar(trend=n(), momentum=n(), volatility_risk=n(), setup_quality=n()),
        sentiment=SentimentPillar(retail_sentiment=n(), social_buzz=n(),
                                 consensus_quality=n(), narrative_strength=n()),
        news=NewsPillar(catalyst_strength=n(), macro_alignment=n(),
                       headline_quality=n(), surprise_risk=n()),
        fundamentals=FundamentalsPillar(valuation=n(), growth=n(), profitability=n(),
                                       balance_sheet_strength=n()),
    )


def _assemble(
    ticker: str,
    as_of_date: str,
    facts: FactSnapshot,
    pillars: PillarScores,
    peer_pct: Dict[str, Optional[float]],
    flags: List[str],
    source: str,
) -> StockDimensions:
    factors, factor_flags = compute_factors_with_flags(
        pillars, _facts_to_peer_dict(facts), peer_pct
    )
    all_flags = list(flags) + factor_flags
    return StockDimensions(
        ticker=ticker,
        as_of_date=as_of_date,
        facts=facts,
        pillar_scores=pillars,
        factor_scores=factors,
        dimensions_version=DIMENSIONS_VERSION,
        peer_universe_id=peer_universe_id(facts.sector, facts.industry),
        data_quality_flags=all_flags,
        source=source,  # type: ignore[arg-type]
    )


def build_dimensions(
    *,
    ticker: str,
    as_of_date: str,
    analyst_reports: Dict[str, str],
    llm: Any,
    config: Optional[Dict[str, Any]] = None,
) -> StockDimensions:
    try:
        facts, flags = extract_facts(ticker, as_of_date)
    except FactExtractionError as exc:
        raise DimensionsBuildError(f"Fact extraction failed: {exc}") from exc

    cache_dir = _get_peer_cache_dir(config)
    _peer_tickers, peer_facts_map = _load_or_refresh_peers(
        facts.sector, facts.industry, cache_dir,
    )
    peer_pct = build_peer_pct_table(
        target_facts=_facts_to_peer_dict(facts),
        peer_facts=list(peer_facts_map.values()),
        inverted_fields=INVERTED_PEER_FIELDS,
    )

    try:
        pillars = score_pillars(facts=facts, analyst_reports=analyst_reports, llm=llm)
    except PillarScoringError as exc:
        raise DimensionsBuildError(f"Pillar scoring failed: {exc}") from exc

    return _assemble(ticker, as_of_date, facts, pillars, peer_pct, flags, "full_run")


def build_dimensions_facts_only(
    *,
    ticker: str,
    as_of_date: str,
    config: Optional[Dict[str, Any]] = None,
) -> StockDimensions:
    """No LLM, no analyst reports. Pillars defaulted to 3 (neutral)."""
    try:
        facts, flags = extract_facts(ticker, as_of_date)
    except FactExtractionError as exc:
        raise DimensionsBuildError(f"Fact extraction failed: {exc}") from exc

    cache_dir = _get_peer_cache_dir(config)
    _peer_tickers, peer_facts_map = _load_or_refresh_peers(
        facts.sector, facts.industry, cache_dir,
    )
    peer_pct = build_peer_pct_table(
        target_facts=_facts_to_peer_dict(facts),
        peer_facts=list(peer_facts_map.values()),
        inverted_fields=INVERTED_PEER_FIELDS,
    )
    return _assemble(
        ticker, as_of_date, facts, _neutral_pillars(), peer_pct, flags, "facts_only"
    )


def build_commentary(
    *,
    dimensions: StockDimensions,
    pm_decision_text: str,
    llm: Any,
) -> DimensionsCommentary:
    try:
        return _bc(dimensions=dimensions, pm_decision_text=pm_decision_text, llm=llm)
    except CommentaryError as exc:
        raise DimensionsBuildError(f"Commentary failed: {exc}") from exc
