"""Topics persistence via StateStore."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.topics_models import (
    Topic,
    TopicArticle,
    TopicCadence,
    TopicRun,
    TopicRunStatus,
    TopicSource,
    TopicSummary,
    TickerCandidate,
)

logger = logging.getLogger(__name__)

CATALOG_KEY = "topics:catalog"
REVERSE_INDEX_KEY = "topics:reverse_index"
RUN_KEY_PREFIX = "topics:run:"
BUDGET_KEY_PREFIX = "topics:budget:"
MAX_RUN_HISTORY = 14

_SEED_PATH = Path(__file__).resolve().parent / "data" / "topics_seed.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slugify(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:64] or "topic"


def _run_key(run_id: str) -> str:
    return f"{RUN_KEY_PREFIX}{run_id}"


def _budget_key(day: str) -> str:
    return f"{BUDGET_KEY_PREFIX}{day}"


class TopicsStore:
    def __init__(self, state_store) -> None:
        self._store = state_store

    # --- catalog ---

    def list_topics(self) -> List[Topic]:
        raw = self._store.get_json(CATALOG_KEY)
        if not isinstance(raw, list):
            return []
        out: List[Topic] = []
        for item in raw:
            try:
                out.append(Topic.model_validate(item))
            except Exception:
                continue
        return out

    def get_topic(self, topic_id: str) -> Optional[Topic]:
        for t in self.list_topics():
            if t.id == topic_id:
                return t
        return None

    def save_topic(self, topic: Topic) -> Topic:
        topics = self.list_topics()
        replaced = False
        for i, t in enumerate(topics):
            if t.id == topic.id:
                topics[i] = topic
                replaced = True
                break
        if not replaced:
            topics.append(topic)
        self._store.put_json(CATALOG_KEY, [t.model_dump(mode="json") for t in topics])
        return topic

    def delete_topic(self, topic_id: str) -> bool:
        topics = self.list_topics()
        new_list = [t for t in topics if t.id != topic_id]
        if len(new_list) == len(topics):
            return False
        self._store.put_json(CATALOG_KEY, [t.model_dump(mode="json") for t in new_list])
        idx = self._load_reverse_index()
        idx.pop(topic_id, None)
        self._store.put_json(REVERSE_INDEX_KEY, idx)
        return True

    def upsert_by_query(
        self,
        query: str,
        *,
        label: Optional[str] = None,
        cadence: TopicCadence = TopicCadence.daily,
        source: TopicSource = TopicSource.user,
    ) -> Topic:
        q = query.strip()
        slug = _slugify(label or q)
        now = _utc_now_iso()
        for t in self.list_topics():
            if t.query.strip().lower() == q.lower():
                t.label = label or t.label
                t.cadence = cadence
                t.updated_at = now
                return self.save_topic(t)
        topic_id = slug
        existing_ids = {t.id for t in self.list_topics()}
        if topic_id in existing_ids:
            topic_id = f"{slug}-{uuid.uuid4().hex[:6]}"
        topic = Topic(
            id=topic_id,
            label=(label or q).strip(),
            query=q,
            cadence=cadence,
            pinned=False,
            source=source,
            created_at=now,
            updated_at=now,
        )
        return self.save_topic(topic)

    def ensure_seed_topics(self) -> int:
        if self.list_topics():
            return 0
        if not _SEED_PATH.is_file():
            logger.warning("Topics seed file missing: %s", _SEED_PATH)
            return 0
        try:
            raw = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load topics seed: %s", exc)
            return 0
        if not isinstance(raw, list):
            return 0
        count = 0
        now = _utc_now_iso()
        for item in raw:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            query = str(item.get("query") or label).strip()
            if not query:
                continue
            cadence_raw = str(item.get("cadence") or "daily").strip().lower()
            try:
                cadence = TopicCadence(cadence_raw)
            except ValueError:
                cadence = TopicCadence.daily
            topic_id = str(item.get("id") or _slugify(label or query))
            topic = Topic(
                id=topic_id,
                label=label or query,
                query=query,
                cadence=cadence,
                pinned=bool(item.get("pinned")),
                source=TopicSource.seed,
                created_at=now,
                updated_at=now,
            )
            self.save_topic(topic)
            count += 1
        return count

    # --- runs ---

    def _load_reverse_index(self) -> Dict[str, List[str]]:
        raw = self._store.get_json(REVERSE_INDEX_KEY)
        if not isinstance(raw, dict):
            return {}
        out: Dict[str, List[str]] = {}
        for k, v in raw.items():
            if isinstance(v, list):
                out[str(k)] = [str(x) for x in v]
        return out

    def _save_reverse_index(self, idx: Dict[str, List[str]]) -> None:
        self._store.put_json(REVERSE_INDEX_KEY, idx)

    def save_run(self, run: TopicRun) -> TopicRun:
        self._store.put_json(_run_key(run.run_id), run.model_dump(mode="json"))
        idx = self._load_reverse_index()
        runs = idx.get(run.topic_id, [])
        if run.run_id not in runs:
            runs.insert(0, run.run_id)
        idx[run.topic_id] = runs[:MAX_RUN_HISTORY]
        self._save_reverse_index(idx)
        return run

    def get_run(self, run_id: str) -> Optional[TopicRun]:
        raw = self._store.get_json(_run_key(run_id))
        if not isinstance(raw, dict):
            return None
        try:
            return TopicRun.model_validate(raw)
        except Exception:
            return None

    def list_runs(self, topic_id: str, *, limit: int = MAX_RUN_HISTORY) -> List[TopicRun]:
        idx = self._load_reverse_index()
        run_ids = idx.get(topic_id, [])[:limit]
        out: List[TopicRun] = []
        for rid in run_ids:
            run = self.get_run(rid)
            if run is not None:
                out.append(run)
        return out

    def latest_run(self, topic_id: str) -> Optional[TopicRun]:
        runs = self.list_runs(topic_id, limit=1)
        return runs[0] if runs else None

    # --- budget ---

    def get_budget_count(self, day: str) -> int:
        raw = self._store.get_json(_budget_key(day))
        if isinstance(raw, dict):
            return int(raw.get("count") or 0)
        if isinstance(raw, int):
            return raw
        return 0

    def increment_budget(self, day: str) -> int:
        count = self.get_budget_count(day) + 1
        self._store.put_json(_budget_key(day), {"count": count, "day": day})
        return count

    # --- summaries ---

    def list_summaries(self) -> List[TopicSummary]:
        summaries: List[TopicSummary] = []
        for topic in self.list_topics():
            latest = self.latest_run(topic.id)
            candidates: List[TickerCandidate] = []
            count = 0
            if latest and latest.status == TopicRunStatus.completed:
                candidates = latest.candidates[:5]
                count = len(latest.candidates)
            summaries.append(
                TopicSummary(
                    id=topic.id,
                    label=topic.label,
                    query=topic.query,
                    cadence=topic.cadence,
                    pinned=topic.pinned,
                    source=topic.source,
                    last_run_at=topic.last_run_at,
                    candidate_count=count,
                    top_candidates=candidates,
                )
            )
        return summaries


_store: Optional[TopicsStore] = None


def get_topics_store(state_store=None) -> TopicsStore:
    global _store
    if state_store is not None:
        _store = TopicsStore(state_store)
    elif _store is None:
        from api.state_store import get_state_store

        _store = TopicsStore(get_state_store())
    return _store


def reset_topics_store_for_tests() -> None:
    global _store
    _store = None
