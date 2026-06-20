"""Topics orchestrator and 60s refresh scheduler."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from api.tavily import (
    TavilyAuthError,
    TavilyError,
    TavilyRateLimitError,
    get_tavily_daily_cap,
    search as tavily_search,
)
from api.topics_extract import extract_from_articles
from api.topics_models import (
    Topic,
    TopicArticle,
    TopicCadence,
    TopicRun,
    TopicRunStatus,
    TopicSource,
)
from api.topics_store import TopicsStore, get_topics_store, _utc_now_iso
from api.notifications import get_manager

logger = logging.getLogger(__name__)

REFRESH_COOLDOWN = timedelta(minutes=5)

_engine: Optional["TopicsEngine"] = None


class TopicsBudgetExceeded(Exception):
    """Daily Tavily budget exhausted."""


class TopicsRefreshCooldown(Exception):
    """Topic refreshed too recently."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Refresh cooldown active ({retry_after_seconds}s remaining)")


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_due(topic: Topic, now: datetime) -> bool:
    if topic.cadence == TopicCadence.manual:
        return False
    last = _parse_iso(topic.last_run_at)
    if last is None:
        return True
    if topic.cadence == TopicCadence.daily:
        return now - last >= timedelta(hours=24)
    if topic.cadence == TopicCadence.weekly:
        return now - last >= timedelta(days=7)
    return False


class TopicsEngine:
    """Shared primitive for on-demand search and scheduled refresh."""

    def __init__(self, service_config: dict, store: Optional[TopicsStore] = None) -> None:
        self.service_config = service_config
        self.store = store or get_topics_store()
        self._task: Optional[asyncio.Task] = None
        self._last_tick: Optional[str] = None
        self._last_errors: List[str] = []

    def status(self) -> dict[str, Any]:
        day = _today_utc()
        status = {
            "enabled": True,
            "poll_seconds": 60,
            "last_tick": self._last_tick,
            "topic_count": len(self.store.list_topics()),
            "tavily_budget_today": self.store.get_budget_count(day),
            "tavily_daily_cap": get_tavily_daily_cap(),
            "last_errors": self._last_errors[-5:],
        }
        # Include regime snapshot when pre-filter is enabled
        if self.service_config.get("regime_prefilter_enabled"):
            from api.hpm import compute_hpm_score
            regime = compute_hpm_score()
            status["regime_snapshot"] = regime.model_dump(mode="json")
            status["regime_prefilter_mode"] = self.service_config.get("regime_prefilter_mode", "observe")
        return status

    async def start(self) -> None:
        self.store.ensure_seed_topics()
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick_due_topics()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("topics scheduler error: %s", exc)
                self._last_errors.append(str(exc))
            await asyncio.sleep(60)

    async def _tick_due_topics(self) -> None:
        self._last_tick = _utc_now_iso()
        now = datetime.now(timezone.utc)
        for topic in self.store.list_topics():
            if not _is_due(topic, now):
                continue
            try:
                await self.refresh_topic(topic.id, skip_cooldown=True, scheduled=True)
            except TopicsBudgetExceeded:
                logger.info("Topics scheduler stopped: daily Tavily budget exhausted")
                await get_manager().send(
                    title="Topics scheduler paused",
                    body="Daily Tavily budget exhausted. Scheduled topic refreshes are paused until tomorrow.",
                    tags=["topics", "budget"],
                )
                return
            except Exception as exc:
                self._last_errors.append(f"{topic.id}: {exc}")
                logger.exception("Topics refresh failed for %s", topic.id)
                await get_manager().send(
                    title=f"Topics refresh failed: {topic.id}",
                    body=f"Scheduled refresh failed with: {exc}",
                    tags=["topics", topic.id],
                )

    def _check_budget(self) -> None:
        day = _today_utc()
        cap = get_tavily_daily_cap()
        if self.store.get_budget_count(day) >= cap:
            raise TopicsBudgetExceeded(f"Daily Tavily cap ({cap}) reached")

    def _check_cooldown(self, topic: Topic, *, skip: bool) -> None:
        if skip:
            return
        last = _parse_iso(topic.last_refresh_at)
        if last is None:
            return
        elapsed = datetime.now(timezone.utc) - last
        if elapsed < REFRESH_COOLDOWN:
            remaining = int((REFRESH_COOLDOWN - elapsed).total_seconds())
            raise TopicsRefreshCooldown(max(1, remaining))

    async def refresh_topic(
        self,
        topic_id: str,
        *,
        skip_cooldown: bool = False,
        scheduled: bool = False,
    ) -> TopicRun:
        topic = self.store.get_topic(topic_id)
        if topic is None:
            raise KeyError(f"Topic not found: {topic_id}")

        self._check_budget()
        self._check_cooldown(topic, skip=skip_cooldown)

        run_id = uuid.uuid4().hex[:12]
        started = _utc_now_iso()
        run = TopicRun(
            run_id=run_id,
            topic_id=topic_id,
            started_at=started,
            status=TopicRunStatus.running,
        )
        self.store.save_run(run)

        loop = asyncio.get_running_loop()
        try:
            raw_articles = await loop.run_in_executor(
                None, lambda: tavily_search(topic.query, max_results=10)
            )
            self.store.increment_budget(_today_utc())

            articles = [
                TopicArticle(
                    title=a["title"],
                    url=a["url"],
                    snippet=a.get("snippet"),
                    published_at=a.get("published_at"),
                    source=a.get("source"),
                )
                for a in raw_articles
            ]

            extraction = await loop.run_in_executor(
                None,
                lambda: extract_from_articles(articles, topic.query, self.service_config),
            )

            run.articles = articles
            run.candidates = extraction.candidates
            run.theme_summary = extraction.theme_summary
            run.regime_snapshot = extraction.regime_snapshot
            run.regime_adjusted = extraction.regime_adjusted
            run.status = TopicRunStatus.completed
            run.completed_at = _utc_now_iso()
        except (TavilyAuthError, TavilyRateLimitError, TavilyError) as exc:
            run.status = TopicRunStatus.failed
            run.error = str(exc)
            run.completed_at = _utc_now_iso()
            if not scheduled:
                raise
        except Exception as exc:
            run.status = TopicRunStatus.failed
            run.error = str(exc)
            run.completed_at = _utc_now_iso()
            logger.exception("Topic refresh failed for %s", topic_id)
            if not scheduled:
                raise

        self.store.save_run(run)
        topic.last_run_at = run.completed_at or started
        topic.last_refresh_at = run.completed_at or started
        topic.updated_at = _utc_now_iso()
        self.store.save_topic(topic)
        return run

    async def search_and_run(
        self,
        query: str,
        *,
        label: Optional[str] = None,
        cadence: TopicCadence = TopicCadence.daily,
    ) -> tuple[Topic, TopicRun]:
        topic = self.store.upsert_by_query(query, label=label, cadence=cadence, source=TopicSource.user)
        run = await self.refresh_topic(topic.id, skip_cooldown=True)
        return topic, run


def get_topics_engine(service_config=None, state_store=None) -> Optional[TopicsEngine]:
    global _engine
    if service_config is not None:
        from api.topics_store import get_topics_store

        store = get_topics_store(state_store)
        _engine = TopicsEngine(service_config, store)
    return _engine


def reset_topics_engine_for_tests() -> None:
    global _engine
    _engine = None
