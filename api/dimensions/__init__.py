"""Standardized stock dimensions: facts + pillar scores + factor scores.

Computed post-run inside api/ (no edits to tradingagents/). See
docs/superpowers/specs/2026-05-13-standardized-stock-dimensions-design.md.
"""
from api.dimensions.builder import (
    DimensionsBuildError,
    build_commentary,
    build_dimensions,
    build_dimensions_facts_only,
)
from api.dimensions.schemas import (
    DimensionsCommentary,
    FactorScore,
    FactorScores,
    FactSnapshot,
    PillarScore,
    PillarScores,
    StockDimensions,
)
from api.dimensions.version import DIMENSIONS_VERSION

__all__ = [
    "DIMENSIONS_VERSION",
    "DimensionsBuildError",
    "DimensionsCommentary",
    "FactSnapshot",
    "FactorScore",
    "FactorScores",
    "PillarScore",
    "PillarScores",
    "StockDimensions",
    "build_commentary",
    "build_dimensions",
    "build_dimensions_facts_only",
]
