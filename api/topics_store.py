"""Topics persistence — D1 primary with StateStore KV fallback."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, TypeVar

from api.topics_models import (
    Topic,
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

T = TypeVar("T")


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
        self._backfill_attempted = False

    def _d1_enabled(self) -> bool:
        from api.history import d1_history_enabled

        return d1_history_enabled()

    def _try_d1(
        self,
        op_name: str,
        d1_fn: Callable[[], T],
        kv_fn: Callable[[], T],
    ) -> T:
        if not self._d1_enabled():
            return kv_fn()
        try:
            return d1_fn()
        except Exception as exc:
            logger.warning(
                "Topics D1 %s failed, falling back to KV: %s",
                op_name,
                exc,
            )
            return kv_fn()

    def _maybe_backfill_from_kv(self) -> None:
        if self._backfill_attempted or not self._d1_enabled():
            return
        self._backfill_attempted = True
        kv_topics = self._kv_list_topics()
        if not kv_topics:
            return
        try:
            from api import topics_d1

            for topic in kv_topics:
                topics_d1.save_topic(topic)
            idx = self._kv_load_reverse_index()
            for _topic_id, run_ids in idx.items():
                for rid in run_ids:
                    run = self._kv_get_run(rid)
                    if run is not None:
                        topics_d1.save_run(run)
            logger.info(
                "Topics lazy backfill: migrated %d topics from KV to D1",
                len(kv_topics),
            )
        except Exception as exc:
            logger.warning("Topics KV->D1 lazy backfill failed: %s", exc)

    # --- catalog ---

    def list_topics(self) -> List[Topic]:
        def d1_list() -> List[Topic]:
            from api import topics_d1

            topics = topics_d1.list_topics()
            if not topics:
                self._maybe_backfill_from_kv()
                topics = topics_d1.list_topics()
            return topics

        return self._try_d1("list_topics", d1_list, self._kv_list_topics)

    def get_topic(self, topic_id: str) -> Optional[Topic]:
        def d1_get() -> Optional[Topic]:
            from api import topics_d1

            topic = topics_d1.get_topic(topic_id)
            if topic is None:
                self._maybe_backfill_from_kv()
                topic = topics_d1.get_topic(topic_id)
            return topic

        return self._try_d1("get_topic", d1_get, lambda: self._kv_get_topic(topic_id))

    def save_topic(self, topic: Topic) -> Topic:
        def d1_save() -> Topic:
            from api import topics_d1

            return topics_d1.save_topic(topic)

        return self._try_d1("save_topic", d1_save, lambda: self._kv_save_topic(topic))

    def delete_topic(self, topic_id: str) -> bool:
        def d1_delete() -> bool:
            from api import topics_d1

            return topics_d1.delete_topic(topic_id)

        return self._try_d1(
            "delete_topic",
            d1_delete,
            lambda: self._kv_delete_topic(topic_id),
        )

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

    # --- KV catalog ---

    def _kv_list_topics(self) -> List[Topic]:
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

    def _kv_get_topic(self, topic_id: str) -> Optional[Topic]:
        for t in self._kv_list_topics():
            if t.id == topic_id:
                return t
        return None

    def _kv_save_topic(self, topic: Topic) -> Topic:
        topics = self._kv_list_topics()
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

    def _kv_delete_topic(self, topic_id: str) -> bool:
        topics = self._kv_list_topics()
        new_list = [t for t in topics if t.id != topic_id]
        if len(new_list) == len(topics):
            return False
        self._store.put_json(CATALOG_KEY, [t.model_dump(mode="json") for t in new_list])
        idx = self._kv_load_reverse_index()
        idx.pop(topic_id, None)
        self._store.put_json(REVERSE_INDEX_KEY, idx)
        return True

    # --- runs ---

    def _kv_load_reverse_index(self) -> Dict[str, List[str]]:
        raw = self._store.get_json(REVERSE_INDEX_KEY)
        if not isinstance(raw, dict):
            return {}
        out: Dict[str, List[str]] = {}
        for k, v in raw.items():
            if isinstance(v, list):
                out[str(k)] = [str(x) for x in v]
        return out

    def _kv_save_reverse_index(self, idx: Dict[str, List[str]]) -> None:
        self._store.put_json(REVERSE_INDEX_KEY, idx)

    def save_run(self, run: TopicRun) -> TopicRun:
        def d1_save() -> TopicRun:
            from api import topics_d1

            return topics_d1.save_run(run)

        return self._try_d1("save_run", d1_save, lambda: self._kv_save_run(run))

    def get_run(self, run_id: str) -> Optional[TopicRun]:
        def d1_get() -> Optional[TopicRun]:
            from api import topics_d1

            run = topics_d1.get_run(run_id)
            if run is None:
                self._maybe_backfill_from_kv()
                run = topics_d1.get_run(run_id)
            return run

        return self._try_d1("get_run", d1_get, lambda: self._kv_get_run(run_id))

    def list_runs(self, topic_id: str, *, limit: int = MAX_RUN_HISTORY) -> List[TopicRun]:
        def d1_list() -> List[TopicRun]:
            from api import topics_d1

            runs = topics_d1.list_runs(topic_id, limit=limit)
            if not runs:
                self._maybe_backfill_from_kv()
                runs = topics_d1.list_runs(topic_id, limit=limit)
            return runs

        return self._try_d1(
            "list_runs",
            d1_list,
            lambda: self._kv_list_runs(topic_id, limit=limit),
        )

    def latest_run(self, topic_id: str) -> Optional[TopicRun]:
        runs = self.list_runs(topic_id, limit=1)
        return runs[0] if runs else None

    def _kv_save_run(self, run: TopicRun) -> TopicRun:
        self._store.put_json(_run_key(run.run_id), run.model_dump(mode="json"))
        idx = self._kv_load_reverse_index()
        runs = idx.get(run.topic_id, [])
        if run.run_id not in runs:
            runs.insert(0, run.run_id)
        idx[run.topic_id] = runs[:MAX_RUN_HISTORY]
        self._kv_save_reverse_index(idx)
        return run

    def _kv_get_run(self, run_id: str) -> Optional[TopicRun]:
        raw = self._store.get_json(_run_key(run_id))
        if not isinstance(raw, dict):
            return None
        try:
            return TopicRun.model_validate(raw)
        except Exception:
            return None

    def _kv_list_runs(self, topic_id: str, *, limit: int = MAX_RUN_HISTORY) -> List[TopicRun]:
        idx = self._kv_load_reverse_index()
        run_ids = idx.get(topic_id, [])[:limit]
        out: List[TopicRun] = []
        for rid in run_ids:
            run = self._kv_get_run(rid)
            if run is not None:
                out.append(run)
        return out

    # --- budget ---

    def get_budget_count(self, day: str) -> int:
        def d1_get() -> int:
            from api import topics_d1

            return topics_d1.get_budget_count(day)

        return self._try_d1(
            "get_budget_count",
            d1_get,
            lambda: self._kv_get_budget_count(day),
        )

    def increment_budget(self, day: str) -> int:
        def d1_inc() -> int:
            from api import topics_d1

            return topics_d1.increment_budget(day)

        return self._try_d1(
            "increment_budget",
            d1_inc,
            lambda: self._kv_increment_budget(day),
        )

    def _kv_get_budget_count(self, day: str) -> int:
        raw = self._store.get_json(_budget_key(day))
        if isinstance(raw, dict):
            return int(raw.get("count") or 0)
        if isinstance(raw, int):
            return raw
        return 0

    def _kv_increment_budget(self, day: str) -> int:
        count = self._kv_get_budget_count(day) + 1
        self._store.put_json(_budget_key(day), {"count": count, "day": day})
        return count

    # --- summaries ---

    def list_summaries(self) -> List[TopicSummary]:
        summaries: List[TopicSummary] = []
        for topic in self.list_topics():
            latest = self.latest_run(topic.id)
            candidates: List[TickerCandidate] = []
            count = 0
            regime_snapshot = None
            regime_adjusted = False
            topic_regime_adjusted_score = None
            if latest and latest.status == TopicRunStatus.completed:
                candidates = latest.candidates[:5]
                count = len(latest.candidates)
                regime_snapshot = latest.regime_snapshot
                regime_adjusted = latest.regime_adjusted
                # Compute backend-derived topic score for stable ranking
                if candidates:
                    base_score = sum(c.confidence for c in candidates) / len(candidates)
                    if regime_adjusted and regime_snapshot:
                        confidence = regime_snapshot.get("regime_confidence", 1.0)
                        # Use default multiplier 1.0 for topic-level scoring
                        topic_regime_adjusted_score = round(base_score * 1.0 * confidence, 3)
                    else:
                        topic_regime_adjusted_score = round(base_score, 3)
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
                    topic_regime_adjusted_score=topic_regime_adjusted_score,
                    regime_snapshot=regime_snapshot,
                    regime_adjusted=regime_adjusted,
                )
            )
        # Stable server-side ranking: pinned first, then by regime-adjusted score desc
        summaries.sort(
            key=lambda s: (
                not s.pinned,  # False (pinned) sorts before True
                -(s.topic_regime_adjusted_score or 0.0),
                s.label,
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
