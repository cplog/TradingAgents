from pathlib import Path
from typing import Any, Optional

from api.jobs import JobStore
from api.state_store import LocalFileStateStore, StateStore


class _CountingStateStore(StateStore):
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self.put_counts: dict[str, int] = {}

    def get_str(self, key: str) -> Optional[str]:
        val = self._data.get(key)
        if val is None:
            return None
        if isinstance(val, str):
            return val
        import json

        return json.dumps(val, ensure_ascii=False)

    def put_str(self, key: str, value: str) -> None:
        import json

        self.put_counts[key] = self.put_counts.get(key, 0) + 1
        try:
            self._data[key] = json.loads(value)
        except json.JSONDecodeError:
            self._data[key] = value


def test_jobstore_restores_completed_job_after_restart(tmp_path: Path):
    state_path = tmp_path / "api_state.json"
    store_a = LocalFileStateStore(path=state_path)
    jobs_a = JobStore(ttl_hours=24, state_store=store_a)
    jid = jobs_a.create("AAPL", "2026-05-14", {"llm_provider": "openai"})
    jobs_a.append_progress(jid, "started", stage="running")
    jobs_a.set_result(jid, {"rating": "hold"})

    # Simulate a fresh process with the same persisted state backend.
    store_b = LocalFileStateStore(path=state_path)
    jobs_b = JobStore(ttl_hours=24, state_store=store_b)
    restored = jobs_b.get(jid)

    assert restored is not None
    assert restored.status == "completed"
    assert restored.result == {"rating": "hold"}
    assert restored.ticker == "AAPL"


def test_jobstore_marks_inflight_as_failed_after_restart(tmp_path: Path):
    state_path = tmp_path / "api_state.json"
    store_a = LocalFileStateStore(path=state_path)
    jobs_a = JobStore(ttl_hours=24, state_store=store_a)
    jid = jobs_a.create("MSFT", "2026-05-14", {"llm_provider": "openai"})
    jobs_a.update_status(jid, "running")

    store_b = LocalFileStateStore(path=state_path)
    jobs_b = JobStore(ttl_hours=24, state_store=store_b)
    restored = jobs_b.get(jid)

    assert restored is not None
    assert restored.status == "failed"
    assert "Service restarted before this job finished." in (restored.error or "")


def test_jobstore_clear_persisted_only_keeps_memory(tmp_path: Path):
    state_path = tmp_path / "api_state.json"
    store = LocalFileStateStore(path=state_path)
    jobs = JobStore(ttl_hours=24, state_store=store)
    jid = jobs.create("NVDA", "2026-05-14", {"llm_provider": "openai"})

    removed = jobs.clear(clear_memory=False, clear_persisted=True)
    assert removed == 0
    assert jobs.get(jid) is not None

    # Fresh store should no longer restore this job from persistence.
    store2 = LocalFileStateStore(path=state_path)
    jobs2 = JobStore(ttl_hours=24, state_store=store2)
    assert jobs2.get(jid) is None


def test_jobstore_index_not_rewritten_on_progress_updates():
    store = _CountingStateStore()
    jobs = JobStore(ttl_hours=24, state_store=store)
    jid = jobs.create("AAPL", "2026-05-14", {"llm_provider": "openai"})

    # Progress updates persist the job record but should not rewrite jobs:index.
    jobs.append_progress(jid, "step 1", stage="running")
    jobs.append_progress(jid, "step 2", stage="running")
    jobs.append_progress(jid, "step 3", stage="running")

    assert store.put_counts.get("jobs:index", 0) == 1


def test_jobstore_prune_skips_index_write_when_unchanged():
    store = _CountingStateStore()
    jobs = JobStore(ttl_hours=24, state_store=store)
    jid = jobs.create("MSFT", "2026-05-14", {"llm_provider": "openai"})

    initial_index_writes = store.put_counts.get("jobs:index", 0)
    # get() triggers _prune(); with no stale IDs, index should remain unchanged.
    assert jobs.get(jid) is not None
    assert store.put_counts.get("jobs:index", 0) == initial_index_writes
