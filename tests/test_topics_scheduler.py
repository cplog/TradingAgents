"""Topics scheduler / engine tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from api.state_store import LocalFileStateStore, reset_state_store_for_tests
from api.topics import TopicsEngine, _is_due
from api.topics_models import Topic, TopicCadence, TopicSource
from api.topics_store import TopicsStore, reset_topics_store_for_tests
from api.notifications import get_manager, reset_manager_for_tests
from api.models import NotificationChannel, NotificationConfig


@pytest.mark.unit
def test_is_due_daily():
    now = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)
    topic = Topic(
        id="t",
        label="T",
        query="q",
        cadence=TopicCadence.daily,
        pinned=False,
        source=TopicSource.seed,
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
        last_run_at=(now - timedelta(hours=25)).isoformat(),
    )
    assert _is_due(topic, now) is True
    topic.last_run_at = (now - timedelta(hours=2)).isoformat()
    assert _is_due(topic, now) is False


@pytest.mark.unit
def test_is_due_manual_never():
    now = datetime.now(timezone.utc)
    topic = Topic(
        id="t",
        label="T",
        query="q",
        cadence=TopicCadence.manual,
        pinned=False,
        source=TopicSource.user,
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    )
    assert _is_due(topic, now) is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_engine_budget_exceeded(tmp_path, monkeypatch):
    reset_state_store_for_tests()
    reset_topics_store_for_tests()
    state = LocalFileStateStore(tmp_path / "state.json")
    store = TopicsStore(state)
    from api.topics import TopicsBudgetExceeded, _today_utc

    monkeypatch.setenv("TAVILY_DAILY_CAP", "1")
    store.increment_budget(_today_utc())
    engine = TopicsEngine({"llm_provider": "openai"}, store)
    topic = store.upsert_by_query("budget test")
    with pytest.raises(TopicsBudgetExceeded):
        await engine.refresh_topic(topic.id, skip_cooldown=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_topics_budget_exceeded_sends_notification(tmp_path, monkeypatch):
    reset_state_store_for_tests()
    reset_topics_store_for_tests()
    reset_manager_for_tests()
    state = LocalFileStateStore(tmp_path / "state.json")
    store = TopicsStore(state)
    monkeypatch.setattr("api.state_store.get_state_store", lambda: state)
    monkeypatch.setattr("api.notifications.get_state_store", lambda: state)
    manager = get_manager()
    manager.put_config(
        NotificationConfig(
            enabled=True,
            channels=[
                NotificationChannel(
                    id="c1",
                    type="webhook",
                    name="x",
                    enabled=True,
                    config={"url": "http://example.com/hook"},
                )
            ],
        )
    )
    sent = []

    async def fake_send(title, body, tags=None, force=False):
        sent.append(title)
        return {"sent": True}

    monkeypatch.setattr(manager, "send", fake_send)

    from api.topics import _today_utc

    monkeypatch.setenv("TAVILY_DAILY_CAP", "1")
    store.increment_budget(_today_utc())
    engine = TopicsEngine({"llm_provider": "openai"}, store)
    topic = store.upsert_by_query("budget test")
    print("DEBUG topic", topic)
    print("DEBUG manager config", manager.get_config())
    await engine._tick_due_topics()
    assert any("scheduler paused" in s.lower() for s in sent)
