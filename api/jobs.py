"""In-memory job store + semaphore-protected background worker.

For v1 we use an in-memory dict + asyncio tasks. If you need persistence
across restarts, swap JobStore for Redis / RQ / Celery later without touching
the graph logic.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import threading
from typing import Any, Dict, List, Optional

from tradingagents.graph.trading_graph import TradingAgentsGraph
from api.models import DEFAULT_ANALYST_ORDER, VALID_ANALYST_IDS
from api.dimensions.builder import (
    DimensionsBuildError, build_commentary, build_dimensions,
)

logger = logging.getLogger(__name__)

_MAX_PROGRESS_EVENTS = 500

# graph.propagate() uses tradingagents.dataflows.config set_config() (process-global).
# Serialize synchronous propagation so concurrent API jobs cannot clobber vendor routing.
_propagate_sync_lock = threading.Lock()


def _coerce_analyst_ids(analysts: Optional[list]) -> list:
    """Keep only graph-supported analyst keys, preserve order, dedupe."""
    base = (
        list(analysts)
        if analysts is not None
        else list(DEFAULT_ANALYST_ORDER)
    )
    out: list = []
    seen: set[str] = set()
    for a in base:
        if a in VALID_ANALYST_IDS and a not in seen:
            seen.add(a)
            out.append(a)
    return out if out else list(DEFAULT_ANALYST_ORDER)


@dataclass
class JobRecord:
    job_id: str
    ticker: str
    date: str
    status: str  # queued | running | completed | failed
    created_at: datetime
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    config_snapshot: Dict[str, Any] = field(default_factory=dict)
    progress_events: List[Dict[str, Any]] = field(default_factory=list)
    batch_id: Optional[str] = None
    cancellation_requested: bool = False


class JobStore:
    """In-memory store with TTL pruning."""

    def __init__(self, ttl_hours: int = 24):
        self._jobs: Dict[str, JobRecord] = {}
        self._ttl = timedelta(hours=ttl_hours)
        self._lock = threading.Lock()

    def create(
        self,
        ticker: str,
        date: str,
        config: Dict[str, Any],
        *,
        batch_id: Optional[str] = None,
    ) -> str:
        job_id = str(uuid.uuid4())[:8]
        with self._lock:
            self._jobs[job_id] = JobRecord(
                job_id=job_id,
                ticker=ticker,
                date=date,
                status="queued",
                created_at=datetime.utcnow(),
                config_snapshot={k: v for k, v in config.items() if "key" not in k.lower()},
                batch_id=batch_id,
            )
        return job_id

    def get(self, job_id: str) -> Optional[JobRecord]:
        self._prune()
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec is None:
                return None
            return self._snapshot_record(rec)

    def _snapshot_record(self, rec: JobRecord) -> JobRecord:
        """Return a shallow copy with a copy of progress list for safe reads."""
        return JobRecord(
            job_id=rec.job_id,
            ticker=rec.ticker,
            date=rec.date,
            status=rec.status,
            created_at=rec.created_at,
            result=rec.result,
            error=rec.error,
            config_snapshot=dict(rec.config_snapshot),
            progress_events=list(rec.progress_events),
            batch_id=rec.batch_id,
            cancellation_requested=rec.cancellation_requested,
        )

    def update_status(self, job_id: str, status: str) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec:
                rec.status = status

    def set_result(self, job_id: str, result: Dict[str, Any]) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec:
                rec.status = "completed"
                rec.result = result

    def set_error(self, job_id: str, error: str) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec:
                rec.status = "failed"
                rec.error = error

    def request_cancellation(self, job_id: str) -> bool:
        with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return False
            rec.cancellation_requested = True
            return True

    def is_cancellation_requested(self, job_id: str) -> bool:
        with self._lock:
            rec = self._jobs.get(job_id)
            return bool(rec and rec.cancellation_requested)

    def mark_cancelled(self, job_id: str) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec:
                rec.status = "cancelled"

    def append_progress(
        self,
        job_id: str,
        message: str,
        *,
        stage: str = "info",
        details: Optional[str] = None,
    ) -> None:
        evt: Dict[str, Any] = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "stage": stage,
            "message": message,
        }
        if details:
            evt["details"] = details
        with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return
            rec.progress_events.append(evt)
            if len(rec.progress_events) > _MAX_PROGRESS_EVENTS:
                rec.progress_events = rec.progress_events[-_MAX_PROGRESS_EVENTS:]

    def list_ids(self) -> List[str]:
        self._prune()
        with self._lock:
            return list(self._jobs.keys())

    def by_batch(self, batch_id: str) -> List[JobRecord]:
        self._prune()
        with self._lock:
            out = [self._snapshot_record(r) for r in self._jobs.values() if r.batch_id == batch_id]
        return sorted(out, key=lambda r: r.created_at)

    def read_progress_since(self, job_id: str, after_index: int) -> tuple[List[Dict[str, Any]], int, Optional[str]]:
        """For SSE: return new events, new cursor, and current terminal status if any."""
        self._prune()
        with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return [], after_index, None
            total = len(rec.progress_events)
            chunk = list(rec.progress_events[after_index:])
            st = rec.status
            return chunk, total, st

    def running_count(self) -> int:
        with self._lock:
            return sum(1 for r in self._jobs.values() if r.status == "running")

    def _prune(self) -> None:
        cutoff = datetime.utcnow() - self._ttl
        with self._lock:
            stale = [jid for jid, rec in self._jobs.items() if rec.created_at < cutoff]
            for jid in stale:
                self._jobs.pop(jid, None)


class Worker:
    """Runs TradingAgentsGraph.propagate under a concurrency semaphore."""

    def __init__(self, max_concurrency: int = 3, ttl_hours: int = 24):
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.store = JobStore(ttl_hours=ttl_hours)

    async def submit(
        self,
        ticker: str,
        date: str,
        config: Dict[str, Any],
        analysts: Optional[list] = None,
        *,
        batch_id: Optional[str] = None,
    ) -> str:
        """Enqueue a job and return its id."""
        job_id = self.store.create(ticker, date, config, batch_id=batch_id)
        self.store.append_progress(
            job_id, f"Job {job_id} queued for {ticker} @ {date}", stage="queued"
        )
        asyncio.create_task(self._run(job_id, ticker, date, config, analysts))
        return job_id

    async def _run(
        self,
        job_id: str,
        ticker: str,
        date: str,
        config: Dict[str, Any],
        analysts: Optional[list],
    ) -> None:
        async with self.semaphore:
            self.store.update_status(job_id, "running")
            self.store.append_progress(
                job_id,
                "Starting multi-agent analysis pipeline (analysts → research → trader → risk → PM)…",
                stage="running",
            )
            try:
                loop = asyncio.get_running_loop()
                self.store.append_progress(
                    job_id,
                    "Executing LangGraph propagate() … (this may take several minutes)",
                    stage="running",
                )
                stop_hb = asyncio.Event()

                async def _heartbeat() -> None:
                    start = time.monotonic()
                    while True:
                        try:
                            await asyncio.wait_for(stop_hb.wait(), timeout=45.0)
                            break
                        except asyncio.TimeoutError:
                            elapsed = int(time.monotonic() - start)
                            self.store.append_progress(
                                job_id,
                                f"Still running propagate() — ~{elapsed}s elapsed "
                                "(LLM + yfinance tools; OpenRouter can be slow on free tier).",
                                stage="running",
                            )

                hb_task = asyncio.create_task(_heartbeat())
                try:
                    final_state, rating = await loop.run_in_executor(
                        None,
                        self._propagate_sync,
                        ticker,
                        date,
                        config,
                        analysts,
                    )
                finally:
                    stop_hb.set()
                    hb_task.cancel()
                    try:
                        await hb_task
                    except asyncio.CancelledError:
                        pass

                self.store.append_progress(
                    job_id,
                    "Building report artifact …",
                    stage="running",
                )
                from api.reports import build_result

                result = build_result(
                    final_state=final_state,
                    rating=rating,
                    ticker=ticker,
                    date=date,
                    config=config,
                )

                # --- Dimensions post-pass (failure-isolated) ---
                dimensions_enabled = bool(config.get("dimensions_enabled", True))
                if dimensions_enabled and not self.store.is_cancellation_requested(job_id):
                    try:
                        self.store.append_progress(
                            job_id, "Building dimensions: extracting facts (yfinance)…",
                            stage="dimensions",
                        )
                        self.store.append_progress(
                            job_id,
                            "Building dimensions: loading sector peers…",
                            stage="dimensions",
                        )
                        self.store.append_progress(
                            job_id,
                            "Building dimensions: scoring 16 pillars (1 LLM call)…",
                            stage="dimensions",
                        )
                        from tradingagents.llm_clients import create_llm_client
                        llm_client = create_llm_client(
                            provider=config.get("llm_provider", "openai"),
                            model=config.get("quick_think_llm", "gpt-4o-mini"),
                            base_url=config.get("backend_url"),
                        )
                        llm = llm_client.get_llm()
                        analyst_reports = {
                            "market": final_state.get("market_report") or "",
                            "social": final_state.get("sentiment_report") or "",
                            "news": final_state.get("news_report") or "",
                            "fundamentals": final_state.get("fundamentals_report") or "",
                        }
                        dimensions = await loop.run_in_executor(
                            None,
                            lambda: build_dimensions(
                                ticker=ticker, as_of_date=date,
                                analyst_reports=analyst_reports, llm=llm, config=config,
                            ),
                        )
                        self.store.append_progress(
                            job_id,
                            "Building dimensions: computing 6 factor scores…",
                            stage="dimensions",
                        )
                        if not self.store.is_cancellation_requested(job_id):
                            self.store.append_progress(
                                job_id,
                                "Building dimensions: writing commentary (1 LLM call)…",
                                stage="dimensions",
                            )
                            commentary = await loop.run_in_executor(
                                None,
                                lambda: build_commentary(
                                    dimensions=dimensions,
                                    pm_decision_text=final_state.get("final_trade_decision") or "",
                                    llm=llm,
                                ),
                            )
                            result["dimensions_commentary"] = commentary.model_dump()
                        result["dimensions"] = dimensions.model_dump()
                        self.store.append_progress(
                            job_id,
                            f"Dimensions built (version {dimensions.dimensions_version}). Persisting…",
                            stage="dimensions",
                        )
                    except DimensionsBuildError as exc:
                        logger.warning("Dimensions build failed for %s: %s", job_id, exc)
                        result["dimensions"] = None
                        result["dimensions_commentary"] = None
                        result["dimensions_error"] = str(exc)
                        self.store.append_progress(
                            job_id, f"Dimensions skipped: {exc}",
                            stage="dimensions_skipped",
                        )
                    except Exception as exc:
                        logger.exception("Unexpected dimensions failure for %s", job_id)
                        result["dimensions"] = None
                        result["dimensions_commentary"] = None
                        result["dimensions_error"] = f"{type(exc).__name__}: {exc}"
                        self.store.append_progress(
                            job_id, f"Dimensions skipped: {exc}",
                            stage="dimensions_skipped",
                        )

                if self.store.is_cancellation_requested(job_id):
                    self.store.set_result(job_id, result)
                    self.store.append_progress(
                        job_id, "Job cancelled at stage boundary; partial result returned.",
                        stage="cancelled",
                    )
                else:
                    self.store.set_result(job_id, result)
                try:
                    from api.history import persist_completed_run
                    from api.state_store import get_state_store

                    done = self.store.get(job_id)
                    if done:
                        persist_completed_run(
                            get_state_store(),
                            job_id=job_id,
                            ticker=ticker,
                            date=date,
                            result=result,
                            created_at=done.created_at,
                            batch_id=done.batch_id,
                            config_snapshot=done.config_snapshot,
                        )
                except Exception:
                    logger.exception("History persistence failed for job %s", job_id)
                self.store.append_progress(
                    job_id,
                    f"Completed. Rating: {rating}",
                    stage="completed",
                )
                logger.info("Job %s completed for %s", job_id, ticker)
            except Exception as exc:
                logger.exception("Job %s failed for %s", job_id, ticker)
                self.store.set_error(job_id, f"{type(exc).__name__}: {exc}")
                self.store.append_progress(
                    job_id,
                    f"Failed: {type(exc).__name__}: {exc}",
                    stage="failed",
                )

    def _propagate_sync(
        self,
        ticker: str,
        date: str,
        config: Dict[str, Any],
        analysts: Optional[list],
    ) -> tuple:
        logger.info(
            "propagate() starting | ticker=%s date=%s provider=%s",
            ticker,
            date,
            config.get("llm_provider"),
        )
        selected = _coerce_analyst_ids(analysts)
        with _propagate_sync_lock:
            graph = TradingAgentsGraph(
                selected_analysts=selected,
                config=config,
                debug=False,
            )
            out = graph.propagate(ticker, date)
        logger.info("propagate() finished | ticker=%s", ticker)
        return out


# Global singleton instantiated in api.main startup
worker: Optional[Worker] = None
