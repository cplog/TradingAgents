"""Orchestrator: facts → peers → pillars → factors → StockDimensions."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.dimensions.commentary import CommentaryError, build_commentary as _bc
from api.dimensions.facts import FactExtractionError, extract_facts
from api.dimensions.factors import (
    INVERTED_PEER_FIELDS,
    compute_factors_sentiment_only,
    compute_factors_with_flags,
)
from api.dimensions.peer_resolver import (
    peer_universe_display_label,
    resolve_peer_facts_for_snapshot,
)
from api.dimensions.peers import build_peer_pct_table
from api.dimensions.schemas import (
    DimensionsCommentary,
    FactSnapshot,
    FundamentalsPillar,
    MarketPillar,
    NewsPillar,
    PillarScore,
    PillarScores,
    SentimentPillar,
    StockDimensions,
)
from api.dimensions.scoring import PillarScoringError, score_pillars, score_pillars_separate
from api.dimensions.version import DIMENSIONS_VERSION

logger = logging.getLogger(__name__)


class DimensionsBuildError(RuntimeError):
    pass


def _get_peer_cache_dir(config: Optional[Dict[str, Any]]) -> Path:
    cfg = config or {}
    base = Path(cfg.get("data_cache_dir") or "./data_cache")
    return base / "peer_facts"


_STYLE_PEER_PCT_KEYS = (
    "pe_ttm",
    "pb",
    "eps_growth_yoy",
    "revenue_growth_yoy",
    "roe",
    "interest_coverage",
    "return_3m",
    "return_12m",
    "beta",
)


def _peer_pct_coverage_flags(peer_pct: Dict[str, Optional[float]]) -> List[str]:
    """Surface when peer-relative ranks are thin so UI can label pillar-heavy blends."""
    present = sum(1 for k in _STYLE_PEER_PCT_KEYS if peer_pct.get(k) is not None)
    if present == 0:
        return ["peer_style_percentiles_missing_using_pillar_blend"]
    if present < 4:
        return ["peer_style_percentiles_partial"]
    return []


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
    *,
    peer_resolution_flags: List[str],
    peer_resolution_scope: Optional[str],
    peer_resolution_slug: Optional[str],
    peer_resolution_paths: List[str],
    peer_universe_visible_id: Optional[str],
    peer_pct: Dict[str, Optional[float]],
    peer_row_count: int,
    peer_usable: bool,
    pillar_blend_when_no_peer_universe: bool,
    flags: List[str],
    source: str,
) -> StockDimensions:
    if peer_usable:
        # With ≥3 peers we still blend pillar scores + whatever peer percentiles exist.
        # Strict “peer pct required” mode blanked factors for banks/HK names where yfinance
        # peer ranks are often missing — radar looked “broken” despite valid pillars.
        factors, factor_flags = compute_factors_with_flags(
            pillars,
            _facts_to_peer_dict(facts),
            peer_pct,
            enforce_peer_pct_for_style_factors=False,
        )
        cov_flags = _peer_pct_coverage_flags(peer_pct)
    elif pillar_blend_when_no_peer_universe:
        # Full analysis runs use analyst pillar scores even when peer cache is cold so the
        # radar reflects the same narrative as “Pillar breakdown”. Facts-only snapshots keep
        # sentiment-only factors (neutral pillars would imply fake precision).
        factors, factor_flags = compute_factors_with_flags(
            pillars,
            _facts_to_peer_dict(facts),
            {},
            enforce_peer_pct_for_style_factors=False,
        )
        cov_flags = []
    else:
        factors, factor_flags = compute_factors_sentiment_only(pillars)
        cov_flags = []

    all_flags = (
        list(flags)
        + list(peer_resolution_flags)
        + list(factor_flags)
        + cov_flags
    )

    if not peer_usable and "peer_percentiles_unavailable" not in all_flags:
        all_flags.append("peer_percentiles_unavailable")

    return StockDimensions(
        ticker=ticker,
        as_of_date=as_of_date,
        facts=facts,
        pillar_scores=pillars,
        factor_scores=factors,
        dimensions_version=DIMENSIONS_VERSION,
        peer_universe_id=peer_universe_visible_id,
        peer_scope=peer_resolution_scope,  # type: ignore[arg-type]
        peer_universe_search_path=peer_resolution_paths,
        peer_universe_resolved_slug=peer_resolution_slug,
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
    peer_res = resolve_peer_facts_for_snapshot(facts, cache_dir)
    peer_row_count = peer_res.peer_row_count
    peer_pct = build_peer_pct_table(
        target_facts=_facts_to_peer_dict(facts),
        peer_facts=list(peer_res.facts_by_ticker.values()),
        inverted_fields=INVERTED_PEER_FIELDS,
    )

    peer_usable = peer_row_count >= 3 and peer_res.peer_scope != "unavailable"
    display_label = peer_universe_display_label(peer_res)

    source = "full_run"
    try:
        pillars, pillar_flags = score_pillars_separate(
            facts=facts,
            analyst_reports=analyst_reports,
            llm=llm,
            peer_scope=peer_res.peer_scope,
            data_quality_flags=list(flags),
        )
        if pillar_flags:
            flags = list(flags) + pillar_flags
            logger.warning(
                "Partial pillar scoring for %s (%s): %s",
                ticker, as_of_date, pillar_flags,
            )
    except PillarScoringError as exc:
        logger.warning("Pillar scoring unavailable for %s: %s", ticker, exc)
        flags = list(flags) + [f"pillar_scoring_unavailable: {exc}"]
        pillars = _neutral_pillars()
        source = "facts_only"

    return _assemble(
        ticker,
        as_of_date,
        facts,
        pillars,
        peer_resolution_flags=peer_res.escalation_flags,
        peer_resolution_scope=peer_res.peer_scope,
        peer_resolution_slug=peer_res.slug_used,
        peer_resolution_paths=peer_res.search_path_labels,
        peer_universe_visible_id=display_label,
        peer_pct=peer_pct,
        peer_row_count=peer_row_count,
        peer_usable=peer_usable,
        pillar_blend_when_no_peer_universe=True,
        flags=list(flags),
        source=source,
    )


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
    peer_res = resolve_peer_facts_for_snapshot(facts, cache_dir)
    peer_row_count = peer_res.peer_row_count
    peer_pct = build_peer_pct_table(
        target_facts=_facts_to_peer_dict(facts),
        peer_facts=list(peer_res.facts_by_ticker.values()),
        inverted_fields=INVERTED_PEER_FIELDS,
    )
    peer_usable = peer_row_count >= 3 and peer_res.peer_scope != "unavailable"
    display_label = peer_universe_display_label(peer_res)

    return _assemble(
        ticker,
        as_of_date,
        facts,
        _neutral_pillars(),
        peer_resolution_flags=peer_res.escalation_flags,
        peer_resolution_scope=peer_res.peer_scope,
        peer_resolution_slug=peer_res.slug_used,
        peer_resolution_paths=peer_res.search_path_labels,
        peer_universe_visible_id=display_label,
        peer_pct=peer_pct,
        peer_row_count=peer_row_count,
        peer_usable=peer_usable,
        pillar_blend_when_no_peer_universe=False,
        flags=list(flags),
        source="facts_only",
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
