"""Deterministic Hard Penny Market (HPM) regime scoring service.

Phase 1 implementation: computes a composite 0-5 regime score from
index-trend, breadth, distribution, and leadership signals.  All scoring
is deterministic and reproducible from the same input snapshot.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — formula inputs (keep separate from derived scores)
# ---------------------------------------------------------------------------

SIGNAL_WEIGHTS = {
    "index_trend": 0.30,
    "breadth": 0.25,
    "distribution": 0.25,
    "leadership": 0.20,
}

POSTURE_THRESHOLDS = [
    (4.5, "strong_bull", "Strong bull regime — broad participation, leadership intact."),
    (3.5, "bull", "Bull regime — positive trend with acceptable breadth."),
    (2.5, "neutral", "Neutral regime — mixed signals, no clear edge."),
    (1.5, "caution", "Caution regime — weakening breadth or distribution pressure."),
    (0.0, "hard_penny", "Hard penny regime — defensive posture recommended."),
]

TRANSMISSION_CHAINS = {
    "strong_bull": ["index_trend", "breadth", "leadership"],
    "bull": ["index_trend", "breadth"],
    "neutral": ["breadth", "distribution"],
    "caution": ["distribution", "breadth"],
    "hard_penny": ["distribution", "index_trend", "leadership"],
}

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SignalDetail(BaseModel):
    """Per-signal breakdown."""

    score: float = Field(ge=0.0, le=1.0, description="Raw signal score 0-1")
    direction: str = Field(description="up | down | flat")
    detail: Optional[str] = None


class HPMScoreResult(BaseModel):
    """Structured regime snapshot returned by the scorer."""

    index: str = Field(default="SPY", description="Reference index ticker")
    composite_score: float = Field(
        ge=0.0, le=5.0, description="Composite regime score 0-5"
    )
    signals: Dict[str, SignalDetail] = Field(default_factory=dict)
    trading_posture: str = Field(
        description="One of: strong_bull, bull, neutral, caution, hard_penny"
    )
    regime_confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in the regime classification"
    )
    regime_reason_codes: List[str] = Field(
        default_factory=list,
        description="Human-readable reason codes for the regime",
    )
    dominant_transmission_chain: List[str] = Field(
        default_factory=list,
        description="Ordered signal names driving the regime",
    )
    timestamp: str = Field(description="ISO-8601 UTC timestamp of computation")


# ---------------------------------------------------------------------------
# Scoring internals
# ---------------------------------------------------------------------------

def _compute_index_trend(index: str) -> SignalDetail:
    """Deterministic index-trend signal.

    Phase 1 uses a simplified heuristic based on the index symbol itself so
    the scorer is fully deterministic without requiring live market data.
    In Phase 2 this will be replaced by actual OHLCV-derived trend strength.
    """
    # Deterministic seed from ticker symbol for reproducible tests
    seed = sum(ord(c) for c in index.upper())
    score = 0.5 + 0.3 * ((seed % 7) / 7.0 - 0.5) * 2
    score = round(max(0.0, min(1.0, score)), 3)
    direction = "up" if score > 0.55 else "down" if score < 0.45 else "flat"
    return SignalDetail(
        score=score,
        direction=direction,
        detail=f"Index-trend heuristic for {index} (seed={seed})",
    )


def _compute_breadth(index: str) -> SignalDetail:
    """Deterministic market-breadth signal."""
    seed = sum(ord(c) for c in index.upper()) + 13
    score = 0.5 + 0.25 * ((seed % 5) / 5.0 - 0.5) * 2
    score = round(max(0.0, min(1.0, score)), 3)
    direction = "up" if score > 0.55 else "down" if score < 0.45 else "flat"
    return SignalDetail(
        score=score,
        direction=direction,
        detail=f"Breadth heuristic for {index} (seed={seed})",
    )


def _compute_distribution(index: str) -> SignalDetail:
    """Deterministic distribution/volume-pressure signal."""
    seed = sum(ord(c) for c in index.upper()) + 29
    score = 0.5 + 0.20 * ((seed % 11) / 11.0 - 0.5) * 2
    score = round(max(0.0, min(1.0, score)), 3)
    direction = "up" if score > 0.55 else "down" if score < 0.45 else "flat"
    return SignalDetail(
        score=score,
        direction=direction,
        detail=f"Distribution heuristic for {index} (seed={seed})",
    )


def _compute_leadership(index: str) -> SignalDetail:
    """Deterministic leadership/sector-rotation signal."""
    seed = sum(ord(c) for c in index.upper()) + 37
    score = 0.5 + 0.25 * ((seed % 9) / 9.0 - 0.5) * 2
    score = round(max(0.0, min(1.0, score)), 3)
    direction = "up" if score > 0.55 else "down" if score < 0.45 else "flat"
    return SignalDetail(
        score=score,
        direction=direction,
        detail=f"Leadership heuristic for {index} (seed={seed})",
    )


def _map_posture(composite: float) -> tuple[str, str]:
    """Return (posture_key, posture_description) from composite score."""
    for threshold, key, desc in POSTURE_THRESHOLDS:
        if composite >= threshold:
            return key, desc
    return "hard_penny", POSTURE_THRESHOLDS[-1][2]


def _build_reason_codes(
    signals: Dict[str, SignalDetail], posture: str
) -> List[str]:
    """Generate human-readable reason codes from signal directions."""
    codes: List[str] = []
    for name, sig in signals.items():
        if sig.direction == "down":
            codes.append(f"{name}_weakening")
        elif sig.direction == "up":
            codes.append(f"{name}_positive")
        else:
            codes.append(f"{name}_neutral")
    # Add posture-level code
    if posture == "hard_penny":
        codes.append("composite_below_caution")
    elif posture == "strong_bull":
        codes.append("composite_above_bull")
    return codes


def _dominant_chain(posture: str) -> List[str]:
    """Return the dominant transmission chain for the posture."""
    return list(TRANSMISSION_CHAINS.get(posture, []))


def _regime_confidence(
    composite: float, signals: Dict[str, SignalDetail]
) -> float:
    """Compute confidence as 1 - normalized variance of signal scores.

    High agreement across signals → high confidence.
    Mixed signals → lower confidence.
    """
    values = [s.score for s in signals.values()]
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    # Normalize: max possible variance for [0,1] is 0.25
    normalized_var = min(variance / 0.25, 1.0)
    confidence = round(1.0 - normalized_var, 3)
    return confidence


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_hpm_score(index: str = "SPY") -> HPMScoreResult:
    """Compute deterministic HPM regime snapshot for the given index.

    Args:
        index: Reference index ticker (default SPY).

    Returns:
        HPMScoreResult with composite score, per-signal details, posture,
        reason codes, transmission chain, and confidence.
    """
    signals = {
        "index_trend": _compute_index_trend(index),
        "breadth": _compute_breadth(index),
        "distribution": _compute_distribution(index),
        "leadership": _compute_leadership(index),
    }

    composite = sum(
        signals[name].score * weight for name, weight in SIGNAL_WEIGHTS.items()
    )
    composite = round(composite * 5.0, 3)  # Map weighted avg → 0-5 scale

    posture, _ = _map_posture(composite)
    confidence = _regime_confidence(composite, signals)
    reason_codes = _build_reason_codes(signals, posture)
    chain = _dominant_chain(posture)

    return HPMScoreResult(
        index=index.upper(),
        composite_score=composite,
        signals=signals,
        trading_posture=posture,
        regime_confidence=confidence,
        regime_reason_codes=reason_codes,
        dominant_transmission_chain=chain,
        timestamp=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )


def get_trading_posture(composite_score: float) -> str:
    """Return posture key from a composite score without recomputing signals."""
    posture, _ = _map_posture(composite_score)
    return posture


# ---------------------------------------------------------------------------
# Policy helpers (used by Topics / Analysis integration)
# ---------------------------------------------------------------------------

def get_topic_style_multiplier(
    style: str,
    config: Dict[str, Any],
) -> float:
    """Return regime multiplier for a topic style from config.

    Args:
        style: Topic style key (e.g. 'momentum', 'value', 'defensive').
        config: Service config dict containing ``regime_topic_multipliers``.

    Returns:
        Multiplier float (default 1.0 when not configured or disabled).
    """
    if not config.get("regime_prefilter_enabled"):
        return 1.0
    multipliers = config.get("regime_topic_multipliers") or {}
    return float(multipliers.get(style, multipliers.get("default", 1.0)))


def should_gate_analysis(
    composite_score: float,
    config: Dict[str, Any],
) -> bool:
    """Return True if analysis should be gated in enforce mode.

    Gating triggers when:
    - regime_prefilter_enabled is True
    - regime_prefilter_mode is "enforce"
    - composite_score < regime_enforce_threshold (default 2.5)
    """
    if not config.get("regime_prefilter_enabled"):
        return False
    if config.get("regime_prefilter_mode") != "enforce":
        return False
    threshold = float(config.get("regime_enforce_threshold", 2.5))
    return composite_score < threshold
