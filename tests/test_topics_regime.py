"""Topics regime integration tests.

Validates:
- multiplier application when regime_prefilter_enabled=true
- exact old behavior (no snapshot, no adjusted scores) when disabled
- score decomposition assertions (base, multiplier, confidence, final)
- disable-path parity
"""

from __future__ import annotations

import pytest

from api.state_store import LocalFileStateStore, reset_state_store_for_tests
from api.topics_extract import apply_regime_multipliers, normalize_candidates
from api.topics_models import (
    TickerCandidate,
    TickerMarket,
    TopicRun,
    TopicRunStatus,
    TopicSource,
)
from api.topics_store import TopicsStore, reset_topics_store_for_tests


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: False)
    reset_state_store_for_tests()
    reset_topics_store_for_tests()
    state = LocalFileStateStore(tmp_path / "state.json")
    return TopicsStore(state)


@pytest.fixture
def sample_candidates():
    return [
        TickerCandidate(ticker="AAPL", confidence=0.90, market=TickerMarket.us),
        TickerCandidate(ticker="NVDA", confidence=0.80, market=TickerMarket.us),
        TickerCandidate(ticker="MSFT", confidence=0.70, market=TickerMarket.us),
    ]


@pytest.mark.unit
def test_apply_regime_multipliers_disabled(sample_candidates):
    cfg = {"regime_prefilter_enabled": False}
    adjusted, snapshot = apply_regime_multipliers(sample_candidates, cfg)
    assert snapshot is None
    assert adjusted[0].confidence == pytest.approx(0.90, abs=1e-3)
    assert adjusted[0].base_confidence is None
    assert adjusted[0].style_multiplier is None
    assert adjusted[0].regime_confidence is None


@pytest.mark.unit
def test_apply_regime_multipliers_enabled(sample_candidates):
    cfg = {
        "regime_prefilter_enabled": True,
        "regime_topic_multipliers": {"default": 0.85},
    }
    adjusted, snapshot = apply_regime_multipliers(sample_candidates, cfg)
    assert snapshot is not None
    assert "composite_score" in snapshot
    assert "regime_confidence" in snapshot
    # All candidates should have decomposition fields
    for c in adjusted:
        assert c.base_confidence is not None
        assert c.style_multiplier is not None
        assert c.regime_confidence is not None
        assert c.final_confidence is not None
        # final = base * multiplier * confidence
        expected = c.base_confidence * c.style_multiplier * c.regime_confidence
        assert c.confidence == pytest.approx(min(expected, 1.0), abs=1e-3)


@pytest.mark.unit
def test_apply_regime_multipliers_preserves_order(sample_candidates):
    cfg = {
        "regime_prefilter_enabled": True,
        "regime_topic_multipliers": {"default": 0.85},
    }
    adjusted, _ = apply_regime_multipliers(sample_candidates, cfg)
    # Should still be sorted descending by final confidence
    for i in range(len(adjusted) - 1):
        assert adjusted[i].confidence >= adjusted[i + 1].confidence


@pytest.mark.unit
def test_topic_run_regime_fields(store):
    topic = store.upsert_by_query("test regime theme", source=TopicSource.user)
    run = TopicRun(
        run_id="run-1",
        topic_id=topic.id,
        started_at="2026-06-10T00:00:00+00:00",
        status=TopicRunStatus.completed,
        candidates=[TickerCandidate(ticker="AAPL", confidence=0.9)],
        regime_snapshot={"composite_score": 3.5, "trading_posture": "neutral"},
        regime_adjusted=True,
    )
    store.save_run(run)
    fetched = store.get_run("run-1")
    assert fetched.regime_snapshot is not None
    assert fetched.regime_adjusted is True
    assert fetched.regime_snapshot["composite_score"] == 3.5


@pytest.mark.unit
def test_list_summaries_with_regime_adjusted_score(store):
    topic = store.upsert_by_query("regime summary test", source=TopicSource.user)
    run = TopicRun(
        run_id="run-2",
        topic_id=topic.id,
        started_at="2026-06-10T00:00:00+00:00",
        status=TopicRunStatus.completed,
        candidates=[
            TickerCandidate(ticker="AAPL", confidence=0.9),
            TickerCandidate(ticker="NVDA", confidence=0.8),
        ],
        regime_snapshot={"composite_score": 3.5, "regime_confidence": 0.85},
        regime_adjusted=True,
    )
    store.save_run(run)
    summaries = store.list_summaries()
    summary = next(s for s in summaries if s.id == topic.id)
    assert summary.regime_adjusted is True
    assert summary.regime_snapshot is not None
    assert summary.topic_regime_adjusted_score is not None
    # base = (0.9 + 0.8) / 2 = 0.85; final = 0.85 * 1.0 * 0.85 = 0.7225
    assert summary.topic_regime_adjusted_score == pytest.approx(0.7225, abs=1e-3)


@pytest.mark.unit
def test_list_summaries_without_regime(store):
    topic = store.upsert_by_query("no regime test", source=TopicSource.user)
    run = TopicRun(
        run_id="run-3",
        topic_id=topic.id,
        started_at="2026-06-10T00:00:00+00:00",
        status=TopicRunStatus.completed,
        candidates=[TickerCandidate(ticker="AAPL", confidence=0.9)],
    )
    store.save_run(run)
    summaries = store.list_summaries()
    summary = next(s for s in summaries if s.id == topic.id)
    assert summary.regime_adjusted is False
    assert summary.regime_snapshot is None
    assert summary.topic_regime_adjusted_score == pytest.approx(0.9, abs=1e-3)


@pytest.mark.unit
def test_disable_path_parity(store):
    """When regime is disabled, summaries must match pre-regime behavior exactly."""
    topic = store.upsert_by_query("parity test", source=TopicSource.user)
    run = TopicRun(
        run_id="run-4",
        topic_id=topic.id,
        started_at="2026-06-10T00:00:00+00:00",
        status=TopicRunStatus.completed,
        candidates=[
            TickerCandidate(ticker="AAPL", confidence=0.95),
            TickerCandidate(ticker="GOOGL", confidence=0.85),
        ],
    )
    store.save_run(run)
    summaries = store.list_summaries()
    summary = next(s for s in summaries if s.id == topic.id)
    assert summary.candidate_count == 2
    assert len(summary.top_candidates) == 2
    assert summary.top_candidates[0].ticker == "AAPL"
    assert summary.top_candidates[0].confidence == pytest.approx(0.95, abs=1e-3)
    assert summary.regime_adjusted is False
    assert summary.regime_snapshot is None
    # No extra fields should leak into candidate when disabled
    assert summary.top_candidates[0].base_confidence is None
    assert summary.top_candidates[0].style_multiplier is None
    assert summary.top_candidates[0].regime_confidence is None
