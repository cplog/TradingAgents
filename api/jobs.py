"""In-memory job store + semaphore-protected background worker.

For v1 we use an in-memory dict + asyncio tasks. If you need persistence
across restarts, swap JobStore for Redis / RQ / Celery later without touching
the graph logic.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from api.dimensions.builder import (
    DimensionsBuildError, build_commentary, build_dimensions,
)

logger = logging.getLogger(__name__)


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
    cancellation_requested: bool = False


class JobStore:
    """In-memory store with TTL pruning."""

    def __init__(self, ttl_hours: int = 24):
        self._jobs: Dict[str, JobRecord] = {}
        self._ttl = timedelta(hours=ttl_hours)

    def create(self, ticker: str, date: str, config: Dict[str, Any]) -> str:
        job_id = str(uuid.uuid4())[:8]
        self._jobs[job_id] = JobRecord(
            job_id=job_id,
            ticker=ticker,
            date=date,
            status="queued",
            created_at=datetime.utcnow(),
            config_snapshot={k: v for k, v in config.items() if "key" not in k.lower()},
        )
        return job_id

    def get(self, job_id: str) -> Optional[JobRecord]:
        self._prune()
        return self._jobs.get(job_id)

    def update_status(self, job_id: str, status: str) -> None:
        rec = self._jobs.get(job_id)
        if rec:
            rec.status = status

    def set_result(self, job_id: str, result: Dict[str, Any]) -> None:
        rec = self._jobs.get(job_id)
        if rec:
            rec.status = "completed"
            rec.result = result

    def set_error(self, job_id: str, error: str) -> None:
        rec = self._jobs.get(job_id)
        if rec:
            rec.status = "failed"
            rec.error = error

    def request_cancellation(self, job_id: str) -> bool:
        rec = self._jobs.get(job_id)
        if not rec:
            return False
        rec.cancellation_requested = True
        return True

    def is_cancellation_requested(self, job_id: str) -> bool:
        rec = self._jobs.get(job_id)
        return bool(rec and rec.cancellation_requested)

    def mark_cancelled(self, job_id: str) -> None:
        rec = self._jobs.get(job_id)
        if rec:
            rec.status = "cancelled"

    def _prune(self) -> None:
        cutoff = datetime.utcnow() - self._ttl
        stale = [jid for jid, rec in self._jobs.items() if rec.created_at < cutoff]
        for jid in stale:
            self._jobs.pop(jid, None)


class Worker:
    """Runs TradingAgentsGraph.propagate under a concurrency semaphore."""

    def __init__(self, max_concurrency: int = 3):
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.store = JobStore()

    async def submit(
        self,
        ticker: str,
        date: str,
        config: Dict[str, Any],
        analysts: Optional[list] = None,
    ) -> str:
        """Enqueue a job and return its id."""
        job_id = self.store.create(ticker, date, config)
        # Spawn background task; FastAPI will clean it up on shutdown.
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
            try:
                # TradingAgentsGraph is synchronous; run in thread pool.
                loop = asyncio.get_running_loop()
                final_state, rating = await loop.run_in_executor(
                    None,
                    self._propagate_sync,
                    ticker,
                    date,
                    config,
                    analysts,
                )

                # Build result payload
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
                logger.info("Job %s completed for %s", job_id, ticker)
            except Exception as exc:
                logger.exception("Job %s failed for %s", job_id, ticker)
                self.store.set_error(job_id, f"{type(exc).__name__}: {exc}")

    def _propagate_sync(
        self,
        ticker: str,
        date: str,
        config: Dict[str, Any],
        analysts: Optional[list],
    ) -> tuple:
        selected = analysts or ["market", "social", "news", "fundamentals"]
        graph = TradingAgentsGraph(
            selected_analysts=selected,
            config=config,
            debug=False,
        )
        return graph.propagate(ticker, date)


# Global singleton instantiated in api.main startup
worker: Optional[Worker] = None
