"""Topics D1 persistence, fallback, and lazy backfill tests."""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from api.state_store import LocalFileStateStore, reset_state_store_for_tests
from api.topics_models import TopicCadence, TopicRun, TopicRunStatus, TopicSource, TickerCandidate
from api.topics_store import TopicsStore, reset_topics_store_for_tests


def _topics_ddl(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE topics (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            query TEXT NOT NULL,
            cadence TEXT NOT NULL,
            pinned INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_run_at TEXT,
            last_refresh_at TEXT
        );
        CREATE INDEX idx_topics_updated_at ON topics (updated_at DESC);
        CREATE TABLE topic_runs (
            run_id TEXT PRIMARY KEY,
            topic_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL,
            articles_json TEXT,
            candidates_json TEXT,
            theme_summary TEXT,
            error TEXT
        );
        CREATE INDEX idx_topic_runs_topic_started ON topic_runs (topic_id, started_at DESC);
        CREATE TABLE topic_budgets (
            day TEXT PRIMARY KEY,
            count INTEGER NOT NULL DEFAULT 0
        );
        """
    )


@pytest.fixture
def sqlite_d1(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _topics_ddl(conn)

    def fake_query(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        cur = conn.execute(sql, params or [])
        if cur.description is not None:
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.commit()
        return []

    monkeypatch.setattr("api.history.d1_history_enabled", lambda: True)
    monkeypatch.setattr("api.history._ensure_d1_schema", lambda: None)
    monkeypatch.setattr("api.history._d1_query", fake_query)
    try:
        import api.topics_d1 as topics_d1_mod

        monkeypatch.setattr(topics_d1_mod, "_d1_query", fake_query)
    except ImportError:
        pass
    yield conn
    conn.close()


@pytest.fixture
def d1_store(tmp_path, sqlite_d1):
    reset_state_store_for_tests()
    reset_topics_store_for_tests()
    state = LocalFileStateStore(tmp_path / "state.json")
    return TopicsStore(state)


@pytest.mark.unit
def test_d1_save_and_list_topics(d1_store: TopicsStore):
    topic = d1_store.upsert_by_query("AI chips", label="AI Chips", cadence=TopicCadence.daily)
    assert topic.label == "AI Chips"
    topics = d1_store.list_topics()
    assert len(topics) == 1
    assert topics[0].id == topic.id


@pytest.mark.unit
def test_d1_run_history_cap(d1_store: TopicsStore):
    topic = d1_store.upsert_by_query("test theme")
    for i in range(20):
        run = TopicRun(
            run_id=f"run-{i}",
            topic_id=topic.id,
            started_at=f"2026-05-01T00:{i:02d}:00+00:00",
            status=TopicRunStatus.completed,
            candidates=[TickerCandidate(ticker="AAPL", confidence=0.8)],
        )
        d1_store.save_run(run)
    runs = d1_store.list_runs(topic.id)
    assert len(runs) == 14


@pytest.mark.unit
def test_d1_budget(d1_store: TopicsStore):
    assert d1_store.get_budget_count("2026-05-01") == 0
    assert d1_store.increment_budget("2026-05-01") == 1
    assert d1_store.get_budget_count("2026-05-01") == 1


@pytest.mark.unit
def test_d1_fallback_to_kv_on_error(tmp_path, monkeypatch):
    reset_state_store_for_tests()
    reset_topics_store_for_tests()
    state = LocalFileStateStore(tmp_path / "state.json")
    store = TopicsStore(state)

    monkeypatch.setattr("api.history.d1_history_enabled", lambda: True)

    def boom(*_a, **_k):
        raise RuntimeError("D1 unavailable")

    monkeypatch.setattr("api.history._ensure_d1_schema", lambda: None)
    monkeypatch.setattr("api.history._d1_query", boom)

    topic = store.upsert_by_query("fallback theme")
    assert topic.query == "fallback theme"
    assert store.get_topic(topic.id) is not None


@pytest.mark.unit
def test_lazy_backfill_from_kv_to_d1(tmp_path, monkeypatch, sqlite_d1):
    reset_state_store_for_tests()
    reset_topics_store_for_tests()
    state = LocalFileStateStore(tmp_path / "state.json")

    # Seed data in KV only (D1 disabled).
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: False)
    kv_store = TopicsStore(state)
    topic = kv_store.upsert_by_query("legacy theme", source=TopicSource.user)
    run = TopicRun(
        run_id="legacy-run-1",
        topic_id=topic.id,
        started_at="2026-05-01T12:00:00+00:00",
        status=TopicRunStatus.completed,
        candidates=[TickerCandidate(ticker="MSFT", confidence=0.7)],
    )
    kv_store.save_run(run)

    # Enable D1 and read through store — should backfill from KV.
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: True)
    d1_store = TopicsStore(state)
    topics = d1_store.list_topics()
    assert any(t.id == topic.id for t in topics)
    runs = d1_store.list_runs(topic.id)
    assert len(runs) == 1
    assert runs[0].run_id == "legacy-run-1"

    # Second store instance should read from D1 without re-backfilling.
    d1_store_2 = TopicsStore(state)
    assert d1_store_2.get_topic(topic.id) is not None
    assert d1_store_2.get_run("legacy-run-1") is not None


@pytest.mark.unit
def test_d1_delete_user_topic(d1_store: TopicsStore):
    user = d1_store.upsert_by_query("delete me", source=TopicSource.user)
    assert d1_store.delete_topic(user.id) is True
    assert d1_store.get_topic(user.id) is None
