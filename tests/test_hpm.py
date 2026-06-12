"""HPM (Hard Penny Market) regime scorer unit tests.

Validates deterministic scoring, posture mapping, reason codes,
transmission chains, and confidence computation.
"""

from __future__ import annotations

import pytest

from api.hpm import (
    HPMScoreResult,
    SIGNAL_WEIGHTS,
    _build_reason_codes,
    _compute_breadth,
    _compute_distribution,
    _compute_index_trend,
    _compute_leadership,
    _dominant_chain,
    _map_posture,
    _regime_confidence,
    compute_hpm_score,
    get_topic_style_multiplier,
    get_trading_posture,
    should_gate_analysis,
)


@pytest.mark.unit
class TestSignalComputation:
    """Per-signal deterministic heuristics."""

    def test_index_trend_deterministic(self):
        s1 = _compute_index_trend("SPY")
        s2 = _compute_index_trend("SPY")
        assert s1.score == s2.score
        assert s1.direction == s2.direction
        assert 0.0 <= s1.score <= 1.0

    def test_breadth_deterministic(self):
        s1 = _compute_breadth("QQQ")
        s2 = _compute_breadth("QQQ")
        assert s1.score == s2.score
        assert 0.0 <= s1.score <= 1.0

    def test_distribution_deterministic(self):
        s1 = _compute_distribution("IWM")
        s2 = _compute_distribution("IWM")
        assert s1.score == s2.score
        assert 0.0 <= s1.score <= 1.0

    def test_leadership_deterministic(self):
        s1 = _compute_leadership("DIA")
        s2 = _compute_leadership("DIA")
        assert s1.score == s2.score
        assert 0.0 <= s1.score <= 1.0

    def test_different_indices_produce_different_scores(self):
        """Different index symbols should produce different deterministic seeds."""
        spy = _compute_index_trend("SPY")
        qqq = _compute_index_trend("QQQ")
        # Very unlikely to be identical given different char sums
        assert spy.score != qqq.score


@pytest.mark.unit
class TestPostureMapping:
    """Composite score → posture mapping."""

    def test_strong_bull_threshold(self):
        posture, desc = _map_posture(4.8)
        assert posture == "strong_bull"
        assert get_trading_posture(4.8) == "strong_bull"

    def test_bull_threshold(self):
        posture, desc = _map_posture(4.0)
        assert posture == "bull"
        assert get_trading_posture(4.0) == "bull"

    def test_neutral_threshold(self):
        posture, desc = _map_posture(3.0)
        assert posture == "neutral"
        assert get_trading_posture(3.0) == "neutral"

    def test_caution_threshold(self):
        posture, desc = _map_posture(2.0)
        assert posture == "caution"
        assert get_trading_posture(2.0) == "caution"

    def test_hard_penny_threshold(self):
        posture, desc = _map_posture(1.0)
        assert posture == "hard_penny"
        assert get_trading_posture(1.0) == "hard_penny"
        assert get_trading_posture(0.0) == "hard_penny"


@pytest.mark.unit
class TestReasonCodes:
    """Reason code generation from signal directions."""

    def test_build_reason_codes_positive(self):
        signals = {
            "index_trend": _compute_index_trend("SPY"),
            "breadth": _compute_breadth("SPY"),
        }
        # Force positive direction for test stability
        signals["index_trend"].direction = "up"
        signals["breadth"].direction = "up"
        codes = _build_reason_codes(signals, "strong_bull")
        assert any("positive" in c for c in codes)
        assert "composite_above_bull" in codes

    def test_build_reason_codes_weakening(self):
        signals = {
            "index_trend": _compute_index_trend("SPY"),
            "breadth": _compute_breadth("SPY"),
        }
        signals["index_trend"].direction = "down"
        signals["breadth"].direction = "down"
        codes = _build_reason_codes(signals, "hard_penny")
        assert any("weakening" in c for c in codes)
        assert "composite_below_caution" in codes


@pytest.mark.unit
class TestTransmissionChain:
    """Dominant transmission chain per posture."""

    def test_chain_for_each_posture(self):
        for posture in ("strong_bull", "bull", "neutral", "caution", "hard_penny"):
            chain = _dominant_chain(posture)
            assert isinstance(chain, list)
            assert len(chain) > 0
            assert all(isinstance(c, str) for c in chain)


@pytest.mark.unit
class TestRegimeConfidence:
    """Confidence = 1 - normalized variance."""

    def test_high_agreement_high_confidence(self):
        signals = {
            "a": _compute_index_trend("SPY"),
            "b": _compute_index_trend("SPY"),
        }
        signals["a"].score = 0.8
        signals["b"].score = 0.82
        conf = _regime_confidence(3.0, signals)
        assert conf > 0.9

    def test_low_agreement_low_confidence(self):
        signals = {
            "a": _compute_index_trend("SPY"),
            "b": _compute_index_trend("SPY"),
        }
        signals["a"].score = 0.1
        signals["b"].score = 0.9
        conf = _regime_confidence(3.0, signals)
        assert conf < 0.5


@pytest.mark.unit
class TestComputeHPMScore:
    """End-to-end scorer integration."""

    def test_result_shape(self):
        result = compute_hpm_score("SPY")
        assert isinstance(result, HPMScoreResult)
        assert result.index == "SPY"
        assert 0.0 <= result.composite_score <= 5.0
        assert result.trading_posture in (
            "strong_bull",
            "bull",
            "neutral",
            "caution",
            "hard_penny",
        )
        assert 0.0 <= result.regime_confidence <= 1.0
        assert len(result.regime_reason_codes) > 0
        assert len(result.dominant_transmission_chain) > 0
        assert result.timestamp

    def test_reproducibility(self):
        r1 = compute_hpm_score("QQQ")
        r2 = compute_hpm_score("QQQ")
        assert r1.composite_score == r2.composite_score
        assert r1.trading_posture == r2.trading_posture
        assert r1.regime_confidence == r2.regime_confidence
        assert r1.regime_reason_codes == r2.regime_reason_codes
        assert r1.dominant_transmission_chain == r2.dominant_transmission_chain

    def test_signal_weights_sum_to_one(self):
        assert sum(SIGNAL_WEIGHTS.values()) == pytest.approx(1.0)


@pytest.mark.unit
class TestPolicyHelpers:
    """Config-driven policy helpers."""

    def test_get_topic_style_multiplier_disabled(self):
        cfg = {"regime_prefilter_enabled": False}
        assert get_topic_style_multiplier("momentum", cfg) == 1.0

    def test_get_topic_style_multiplier_enabled(self):
        cfg = {
            "regime_prefilter_enabled": True,
            "regime_topic_multipliers": {"momentum": 0.8, "default": 1.0},
        }
        assert get_topic_style_multiplier("momentum", cfg) == 0.8
        assert get_topic_style_multiplier("unknown", cfg) == 1.0

    def test_should_gate_analysis_disabled(self):
        cfg = {"regime_prefilter_enabled": False}
        assert should_gate_analysis(1.0, cfg) is False

    def test_should_gate_analysis_observe_mode(self):
        cfg = {"regime_prefilter_enabled": True, "regime_prefilter_mode": "observe"}
        assert should_gate_analysis(1.0, cfg) is False

    def test_should_gate_analysis_enforce_below_threshold(self):
        cfg = {
            "regime_prefilter_enabled": True,
            "regime_prefilter_mode": "enforce",
            "regime_enforce_threshold": 2.5,
        }
        assert should_gate_analysis(1.0, cfg) is True
        assert should_gate_analysis(3.0, cfg) is False

    def test_should_gate_analysis_enforce_at_threshold(self):
        cfg = {
            "regime_prefilter_enabled": True,
            "regime_prefilter_mode": "enforce",
            "regime_enforce_threshold": 2.5,
        }
        assert should_gate_analysis(2.5, cfg) is False
