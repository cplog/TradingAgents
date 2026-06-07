import asyncio
import time

import pytest

from api.jobs import JobStore, Worker, _prune_progress_events
from tradingagents.graph.job_control import GraphJobCancelled, GraphJobTimeout, GraphStepHooks


def test_prune_progress_events_drops_heartbeats_before_steps():
    events = [{"kind": "step", "message": f"s{i}"} for i in range(520)]
    events.extend({"kind": "heartbeat", "message": "hb"} for _ in range(20))
    pruned = _prune_progress_events(events)
    assert len(pruned) <= 500
    heartbeat_count = sum(1 for e in pruned if e.get("kind") == "heartbeat")
    step_count = sum(1 for e in pruned if e.get("kind") == "step")
    assert heartbeat_count == 0
    assert step_count == 500


def test_graph_step_hooks_cancel_after_step():
    cancelled = {"flag": False}

    hooks = GraphStepHooks(
        should_cancel=lambda: cancelled["flag"],
        on_step=lambda _node: None,
    )
    hooks.after_step("Market Analyst")
    cancelled["flag"] = True
    with pytest.raises(GraphJobCancelled):
        hooks.after_step("News Analyst")


def test_graph_step_hooks_timeout_after_step():
    started = time.monotonic()

    hooks = GraphStepHooks(
        should_timeout=lambda: (time.monotonic() - started) >= 0.05,
        timeout_seconds=0,
        on_step=lambda _node: None,
    )
    hooks.after_step("Market Analyst")
    time.sleep(0.06)
    with pytest.raises(GraphJobTimeout):
        hooks.after_step("News Analyst")


@pytest.mark.asyncio
async def test_running_job_cancellation_between_steps(monkeypatch):
    worker = Worker(max_concurrency=1, ttl_hours=24)

    def fake_propagate_sync(
        self,
        ticker,
        date,
        config,
        analysts,
        *,
        step_hooks=None,
        **kwargs,
    ):
        assert step_hooks is not None
        step_hooks.on_step("Market Analyst")
        jid = worker.store.list_ids()[0]
        worker.store.request_cancellation(jid)
        with pytest.raises(GraphJobCancelled):
            step_hooks.after_step("News Analyst")
        raise GraphJobCancelled()

    monkeypatch.setattr(Worker, "_propagate_sync", fake_propagate_sync)

    jid = await worker.submit(
        "AAPL",
        "2026-05-13",
        {"checkpoint_enabled": False, "dimensions_enabled": False},
        analysts=["market"],
    )
    for _ in range(100):
        rec = worker.store.get(jid)
        if rec and rec.status in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.05)

    rec = worker.store.get(jid)
    assert rec is not None
    assert rec.status == "cancelled"
    messages = [e.get("message") or "" for e in rec.progress_events]
    assert any("Completed node: Market Analyst" in m for m in messages)
    assert any(e.get("stage") == "cancelled" for e in rec.progress_events)


@pytest.mark.asyncio
async def test_job_timeout_marks_failed(monkeypatch):
    worker = Worker(max_concurrency=1, ttl_hours=24)

    def fake_propagate_sync(
        self,
        ticker,
        date,
        config,
        analysts,
        *,
        step_hooks=None,
        **kwargs,
    ):
        raise GraphJobTimeout(30)

    monkeypatch.setattr(Worker, "_propagate_sync", fake_propagate_sync)

    jid = await worker.submit(
        "AAPL",
        "2026-05-13",
        {"checkpoint_enabled": False, "dimensions_enabled": False},
        analysts=["market"],
    )
    for _ in range(100):
        rec = worker.store.get(jid)
        if rec and rec.status in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.05)

    rec = worker.store.get(jid)
    assert rec is not None
    assert rec.status == "failed"
    assert "timeout" in (rec.error or "").lower()
    assert any("Timed out" in (e.get("message") or "") for e in rec.progress_events)


def test_progress_heartbeat_replaces_previous():
    store = JobStore(ttl_hours=24)
    jid = store.create("AAPL", "2026-05-13", {})
    store.append_progress(jid, "hb-1", kind="heartbeat")
    store.append_progress(jid, "hb-2", kind="heartbeat")
    rec = store.get(jid)
    assert rec is not None
    heartbeats = [e for e in rec.progress_events if e.get("kind") == "heartbeat"]
    assert len(heartbeats) == 1
    assert heartbeats[0]["message"] == "hb-2"
