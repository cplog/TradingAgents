"""Cloudflare D1 persistence for Hot Ideas (Topics)."""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from api.history import _d1_query, _ensure_d1_schema
from api.topics_models import Topic, TopicRun, TopicRunStatus

logger = logging.getLogger(__name__)

MAX_RUN_HISTORY = 14


def _row_to_topic(row: dict[str, Any]) -> Optional[Topic]:
    try:
        return Topic.model_validate(
            {
                "id": row.get("id"),
                "label": row.get("label"),
                "query": row.get("query"),
                "cadence": row.get("cadence"),
                "pinned": bool(row.get("pinned")),
                "source": row.get("source"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "last_run_at": row.get("last_run_at"),
                "last_refresh_at": row.get("last_refresh_at"),
            }
        )
    except Exception as exc:
        logger.warning("Invalid topic row in D1: %s", exc)
        return None


def _row_to_run(row: dict[str, Any]) -> Optional[TopicRun]:
    articles_raw = row.get("articles_json")
    candidates_raw = row.get("candidates_json")
    try:
        articles = (
            json.loads(articles_raw)
            if isinstance(articles_raw, str) and articles_raw
            else []
        )
        candidates = (
            json.loads(candidates_raw)
            if isinstance(candidates_raw, str) and candidates_raw
            else []
        )
        return TopicRun.model_validate(
            {
                "run_id": row.get("run_id"),
                "topic_id": row.get("topic_id"),
                "started_at": row.get("started_at"),
                "completed_at": row.get("completed_at"),
                "status": row.get("status"),
                "articles": articles if isinstance(articles, list) else [],
                "candidates": candidates if isinstance(candidates, list) else [],
                "theme_summary": row.get("theme_summary"),
                "error": row.get("error"),
            }
        )
    except Exception as exc:
        logger.warning("Invalid topic run row in D1: %s", exc)
        return None


def list_topics() -> List[Topic]:
    _ensure_d1_schema()
    rows = _d1_query(
        """
        SELECT id, label, query, cadence, pinned, source,
               created_at, updated_at, last_run_at, last_refresh_at
        FROM topics
        ORDER BY updated_at DESC
        """
    )
    out: List[Topic] = []
    for row in rows:
        topic = _row_to_topic(row)
        if topic is not None:
            out.append(topic)
    return out


def get_topic(topic_id: str) -> Optional[Topic]:
    _ensure_d1_schema()
    rows = _d1_query(
        """
        SELECT id, label, query, cadence, pinned, source,
               created_at, updated_at, last_run_at, last_refresh_at
        FROM topics
        WHERE id = ?
        LIMIT 1
        """,
        [topic_id],
    )
    if not rows:
        return None
    return _row_to_topic(rows[0])


def save_topic(topic: Topic) -> Topic:
    _ensure_d1_schema()
    _d1_query(
        """
        INSERT INTO topics (
            id, label, query, cadence, pinned, source,
            created_at, updated_at, last_run_at, last_refresh_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            label = excluded.label,
            query = excluded.query,
            cadence = excluded.cadence,
            pinned = excluded.pinned,
            source = excluded.source,
            created_at = excluded.created_at,
            updated_at = excluded.updated_at,
            last_run_at = excluded.last_run_at,
            last_refresh_at = excluded.last_refresh_at
        """,
        [
            topic.id,
            topic.label,
            topic.query,
            topic.cadence.value,
            1 if topic.pinned else 0,
            topic.source.value,
            topic.created_at,
            topic.updated_at,
            topic.last_run_at,
            topic.last_refresh_at,
        ],
    )
    return topic


def delete_topic(topic_id: str) -> bool:
    _ensure_d1_schema()
    existing = get_topic(topic_id)
    if existing is None:
        return False
    _d1_query("DELETE FROM topic_runs WHERE topic_id = ?", [topic_id])
    _d1_query("DELETE FROM topics WHERE id = ?", [topic_id])
    return True


def save_run(run: TopicRun) -> TopicRun:
    _ensure_d1_schema()
    _d1_query(
        """
        INSERT INTO topic_runs (
            run_id, topic_id, started_at, completed_at, status,
            articles_json, candidates_json, theme_summary, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
            topic_id = excluded.topic_id,
            started_at = excluded.started_at,
            completed_at = excluded.completed_at,
            status = excluded.status,
            articles_json = excluded.articles_json,
            candidates_json = excluded.candidates_json,
            theme_summary = excluded.theme_summary,
            error = excluded.error
        """,
        [
            run.run_id,
            run.topic_id,
            run.started_at,
            run.completed_at,
            run.status.value,
            json.dumps(
                [a.model_dump(mode="json") for a in run.articles],
                ensure_ascii=False,
            ),
            json.dumps(
                [c.model_dump(mode="json") for c in run.candidates],
                ensure_ascii=False,
            ),
            run.theme_summary,
            run.error,
        ],
    )
    _prune_runs(run.topic_id, MAX_RUN_HISTORY)
    return run


def _prune_runs(topic_id: str, limit: int) -> None:
    _d1_query(
        """
        DELETE FROM topic_runs
        WHERE topic_id = ?
          AND run_id NOT IN (
            SELECT run_id FROM topic_runs
            WHERE topic_id = ?
            ORDER BY started_at DESC
            LIMIT ?
          )
        """,
        [topic_id, topic_id, limit],
    )


def get_run(run_id: str) -> Optional[TopicRun]:
    _ensure_d1_schema()
    rows = _d1_query(
        """
        SELECT run_id, topic_id, started_at, completed_at, status,
               articles_json, candidates_json, theme_summary, error
        FROM topic_runs
        WHERE run_id = ?
        LIMIT 1
        """,
        [run_id],
    )
    if not rows:
        return None
    return _row_to_run(rows[0])


def list_runs(topic_id: str, *, limit: int = MAX_RUN_HISTORY) -> List[TopicRun]:
    _ensure_d1_schema()
    rows = _d1_query(
        """
        SELECT run_id, topic_id, started_at, completed_at, status,
               articles_json, candidates_json, theme_summary, error
        FROM topic_runs
        WHERE topic_id = ?
        ORDER BY started_at DESC
        LIMIT ?
        """,
        [topic_id, limit],
    )
    out: List[TopicRun] = []
    for row in rows:
        run = _row_to_run(row)
        if run is not None:
            out.append(run)
    return out


def latest_run(topic_id: str) -> Optional[TopicRun]:
    runs = list_runs(topic_id, limit=1)
    return runs[0] if runs else None


def get_budget_count(day: str) -> int:
    _ensure_d1_schema()
    rows = _d1_query(
        "SELECT count FROM topic_budgets WHERE day = ? LIMIT 1",
        [day],
    )
    if not rows:
        return 0
    try:
        return int(rows[0].get("count") or 0)
    except (TypeError, ValueError):
        return 0


def increment_budget(day: str) -> int:
    _ensure_d1_schema()
    count = get_budget_count(day) + 1
    _d1_query(
        """
        INSERT INTO topic_budgets (day, count) VALUES (?, ?)
        ON CONFLICT(day) DO UPDATE SET count = excluded.count
        """,
        [day, count],
    )
    return count