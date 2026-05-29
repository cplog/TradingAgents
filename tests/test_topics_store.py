"""Topics store persistence tests."""

from __future__ import annotations

import pytest

from api.state_store import LocalFileStateStore, reset_state_store_for_tests
from api.topics_models import TopicCadence, TopicRun, TopicRunStatus, TopicSource, TickerCandidate
from api.topics_store import TopicsStore, reset_topics_store_for_tests


@pytest.fixture
def store(tmp_path):
    reset_state_store_for_tests()
    reset_topics_store_for_tests()
    state = LocalFileStateStore(tmp_path / "state.json")
    return TopicsStore(state)


@pytest.mark.unit
def test_ensure_seed_topics(store: TopicsStore):
    n = store.ensure_seed_topics()
    assert n >= 10
    topics = store.list_topics()
    assert len(topics) == n
    assert any(t.id == "ai-infrastructure" for t in topics)


@pytest.mark.unit
def test_upsert_by_query(store: TopicsStore):
    t1 = store.upsert_by_query("AI chips", label="AI Chips", cadence=TopicCadence.daily)
    t2 = store.upsert_by_query("ai chips", label="AI Chips Updated")
    assert t1.id == t2.id
    assert t2.label == "AI Chips Updated"


@pytest.mark.unit
def test_run_history_cap(store: TopicsStore):
    topic = store.upsert_by_query("test theme")
    for i in range(20):
        run = TopicRun(
            run_id=f"run-{i}",
            topic_id=topic.id,
            started_at=f"2026-05-01T00:{i:02d}:00+00:00",
            status=TopicRunStatus.completed,
            candidates=[TickerCandidate(ticker="AAPL", confidence=0.8)],
        )
        store.save_run(run)
    runs = store.list_runs(topic.id)
    assert len(runs) == 14


@pytest.mark.unit
def test_budget_tracking(store: TopicsStore):
    assert store.get_budget_count("2026-05-01") == 0
    assert store.increment_budget("2026-05-01") == 1
    assert store.get_budget_count("2026-05-01") == 1


@pytest.mark.unit
def test_delete_user_topic_only(store: TopicsStore):
    store.ensure_seed_topics()
    seed = store.list_topics()[0]
    assert seed.source == TopicSource.seed
    user = store.upsert_by_query("user theme only", source=TopicSource.user)
    assert store.delete_topic(user.id) is True
    assert store.get_topic(user.id) is None
