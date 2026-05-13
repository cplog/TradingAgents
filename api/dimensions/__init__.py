"""Standardized stock dimensions: facts + pillar scores + factor scores.

Computed post-run inside api/ (no edits to tradingagents/). See
docs/superpowers/specs/2026-05-13-standardized-stock-dimensions-design.md.
"""
from api.dimensions.version import DIMENSIONS_VERSION

__all__ = ["DIMENSIONS_VERSION"]
