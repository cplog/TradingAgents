"""Delete paths for orphan index rows and persisted job snapshots."""

from __future__ import annotations

import pytest

from api.history import (
    KEY_GLOBAL_INDEX,
    _delete_kv_run_record,
    _run_key,
    delete_run,
)
from api.jobs import JobStore
from api.state_store import LocalFileStateStore


@pytest.mark.unit
def test_delete_kv_run_record_without_blob_but_index_ref(tmp_path):
    store = LocalFileStateStore(tmp_path / "state.json")
    ref = {
        "run_id": "abc12345",
        "job_id": "abc12345",
        "ticker": "AAPL",
        "date": "2026-05-01",
        "rating": "Hold",
    }
    store.put_json(KEY_GLOBAL_INDEX, [ref])
    assert store.get_json(_run_key("abc12345")) is None
    assert _delete_kv_run_record(store, "abc12345") is True
    assert store.get_json(KEY_GLOBAL_INDEX) == []


@pytest.mark.unit
def test_delete_run_kv_mode_orphan_index(tmp_path):
    store = LocalFileStateStore(tmp_path / "state2.json")
    store.put_json(KEY_GLOBAL_INDEX, [
        {
            "run_id": "deadbeef",
            "job_id": "deadbeef",
            "ticker": "MSFT",
            "date": "2026-05-02",
        }
    ])
    assert delete_run(store, "deadbeef") is True


@pytest.mark.unit
def test_job_store_remove_clears_persisted_snapshot_only(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_JOB_TTL_HOURS", "24")
    state = LocalFileStateStore(tmp_path / "jobs.json")
    jobs = JobStore(ttl_hours=24, state_store=state)
    jid = jobs.create("NVDA", "2026-05-01", {"llm_provider": "openai"})
    jobs.update_status(jid, "completed")
    jobs.set_result(jid, {"rating": "Hold", "confidence": 0.5})
    # Simulate prune dropping in-memory job while KV snapshot remains.
    with jobs._lock:
        jobs._jobs.pop(jid, None)
    assert jobs.remove(jid) is True
    assert jobs.get(jid) is None
