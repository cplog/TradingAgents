from __future__ import annotations

from typing import Optional

import pytest

from api.state_store import FallbackStateStore, StateStore


class _DictStore(StateStore):
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get_str(self, key: str) -> Optional[str]:
        return self.data.get(key)

    def put_str(self, key: str, value: str) -> None:
        self.data[key] = value


class _FailingPutStore(_DictStore):
    def put_str(self, key: str, value: str) -> None:  # pragma: no cover - simple test double
        raise RuntimeError("primary put failed")


@pytest.mark.unit
def test_fallback_store_writes_to_fallback_when_primary_put_fails():
    primary = _FailingPutStore()
    fallback = _DictStore()
    store = FallbackStateStore(primary, fallback, mirror_writes=False)

    store.put_str("history:index:global", "[]")

    assert fallback.get_str("history:index:global") == "[]"


@pytest.mark.unit
def test_fallback_store_reads_from_fallback_when_primary_empty():
    primary = _DictStore()
    fallback = _DictStore()
    fallback.put_str("history:index:global", '[{"run_id":"job-1"}]')
    store = FallbackStateStore(primary, fallback, mirror_writes=False)

    assert store.get_str("history:index:global") == '[{"run_id":"job-1"}]'


@pytest.mark.unit
def test_fallback_store_mirror_writes_updates_both_stores():
    primary = _DictStore()
    fallback = _DictStore()
    store = FallbackStateStore(primary, fallback, mirror_writes=True)

    store.put_str("jobs:index", '["job-1"]')

    assert primary.get_str("jobs:index") == '["job-1"]'
    assert fallback.get_str("jobs:index") == '["job-1"]'
