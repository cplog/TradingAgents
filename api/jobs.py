"""Job store + semaphore-protected background worker.

JobStore keeps an in-memory map for fast runtime access and can optionally
mirror snapshots to ``StateStore`` so job status/progress survives process
restarts (best-effort).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import threading
from typing import Any, Dict, List, Optional

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.graph.checkpointer import checkpoint_step, thread_id
from api.models import DEFAULT_ANALYST_ORDER, VALID_ANALYST_IDS
from api.dimensions.builder import (
    DimensionsBuildError, build_commentary, build_dimensions,
)
from api.state_store import StateStore
from api.kronos import (
    KronosConfig,
    KronosService,
    InsufficientData,
    ModelLoadError,
    KronosDisabled,
    fetch_ohlcv,
    forecast_to_markdown,
    forecast_to_state,
)
from api.kronos.schema import KronosStatus

logger = logging.getLogger(__name__)


def _apply_dimensions_failure(
    result: Dict[str, Any],
    exc: Exception,
    *,
    job_id: str,
) -> None:
    """Keep an existing dimensions snapshot when only commentary generation failed."""
    msg = str(exc)
    if result.get("dimensions"):
        result["dimensions_commentary"] = None
        result["dimensions_error"] = msg
        logger.warning("Dimensions commentary failed for %s: %s", job_id, exc)
        return
    result["dimensions"] = None
    result["dimensions_commentary"] = None
    result["dimensions_error"] = msg
    logger.warning("Dimensions build failed for %s: %s", job_id, exc)


_MAX_PROGRESS_EVENTS = 500
_JOBS_PERSIST_INDEX_KEY = "jobs:index"
_JOBS_PERSIST_PREFIX = "jobs:record:"
_MAX_PERSISTED_JOB_IDS = 1000

# graph.propagate() uses tradingagents.dataflows.config set_config() (process-global).
# Serialize synchronous propagation so concurrent API jobs cannot clobber vendor routing.
_propagate_sync_lock = threading.Lock()

# Style factors from graph snapshots: if a full_run snapshot has none of these scores,
# rerun the expensive dimensions pipeline instead of commentary-only reuse.
_GRAPH_STYLE_FACTOR_KEYS = ("value", "growth", "quality", "momentum", "low_risk")


def _should_rebuild_graph_dimensions_snapshot(snapshot: Dict[str, Any]) -> bool:
    """Return True when a LangGraph dimensions snapshot should be discarded (full rebuild).

    ``facts_only`` snapshots intentionally omit style scores; keep them for commentary-only.
    ``full_run`` snapshots with all style factor scores missing/None are treated as incomplete.
    """
    if not isinstance(snapshot, dict):
        return True
    source = snapshot.get("source") or "full_run"
    if source == "facts_only":
        return False
    raw_factors = snapshot.get("factor_scores")
    if not isinstance(raw_factors, dict):
        return True
    for key in _GRAPH_STYLE_FACTOR_KEYS:
        entry = raw_factors.get(key)
        if not isinstance(entry, dict):
            continue
        if entry.get("score") is not None:
            return False
    return True


def _format_data_routing(config: Dict[str, Any]) -> str:
    """Short description of market-data vendor routing (mirrors dataflows/interface)."""
    dv_raw = config.get("data_vendors") or {}
    tv_raw = config.get("tool_vendors") or {}
    dv: Dict[str, Any] = dv_raw if isinstance(dv_raw, dict) else {}
    tv: Dict[str, Any] = tv_raw if isinstance(tv_raw, dict) else {}

    labels = {
        "core_stock_apis": "OHLCV",
        "technical_indicators": "indicators",
        "fundamental_data": "fundamentals",
        "news_data": "news",
    }
    ordered_keys = (
        "core_stock_apis",
        "technical_indicators",
        "fundamental_data",
        "news_data",
    )
    parts: list[str] = []
    for key in ordered_keys:
        if key in dv and dv[key] is not None and str(dv[key]).strip():
            parts.append(f"{labels[key]}→{dv[key]}")

    if not parts:
        base = "data routing: (category defaults)"
    else:
        vals = {str(v).strip() for v in dv.values() if v is not None and str(v).strip()}
        if len(vals) == 1 and not tv:
            (single,) = vals
            base = f"data routing: all pillars → {single}"
        else:
            base = "data routing: " + ", ".join(parts)

    if tv:
        if len(tv) <= 2:
            overrides = ", ".join(f"{k}→{v}" for k, v in sorted(tv.items()))
            return f"{base}; tool overrides: {overrides}"
        return f"{base}; tool overrides: {len(tv)} tools"

    return base


def _runtime_summary(config: Dict[str, Any]) -> str:
    """Compact, non-secret runtime summary for progress logs."""
    provider = str(config.get("llm_provider") or "openai")
    deep = str(config.get("deep_think_llm") or "")
    quick = str(config.get("quick_think_llm") or "")
    backend = config.get("backend_url")
    backend_label = str(backend).strip() if backend is not None else ""
    if not backend_label:
        backend_label = "default"
    ckpt = "on" if config.get("checkpoint_enabled") else "off"
    dims = "on" if config.get("dimensions_enabled", True) else "off"
    in_graph = config.get("dimensions_in_graph", True)
    dims_detail = f"{dims}" + (", precomputed in graph" if in_graph else ", post-pass only")
    routing = _format_data_routing(config)
    return (
        f"Runtime: LLM={provider}, models deep={deep} / quick={quick}, "
        f"backend={backend_label}, checkpoint={ckpt}, dimensions={dims_detail}. "
        f"{routing}"
    )


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


def _refresh_checkpoint_metadata(rec: JobRecord) -> None:
    """Set resumable / step fields from on-disk LangGraph checkpoint (if any)."""
    cfg = rec.config_snapshot or {}
    if not cfg.get("checkpoint_enabled"):
        rec.resumable = False
        rec.last_graph_step = None
        rec.checkpoint_thread_id = None
        return
    cache_dir = cfg.get("data_cache_dir")
    if not cache_dir:
        rec.resumable = False
        rec.last_graph_step = None
        rec.checkpoint_thread_id = None
        return
    step = checkpoint_step(cache_dir, rec.ticker, rec.date)
    if step is None:
        rec.resumable = False
        rec.last_graph_step = None
        rec.checkpoint_thread_id = None
        return
    rec.resumable = True
    rec.last_graph_step = int(step)
    rec.checkpoint_thread_id = thread_id(rec.ticker, rec.date)


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
    analysts: List[str] = field(default_factory=list)
    resumable: bool = False
    last_graph_step: Optional[int] = None
    checkpoint_thread_id: Optional[str] = None


class JobStore:
    """In-memory store with optional durable snapshots in StateStore."""

    def __init__(self, ttl_hours: int = 24, state_store: Optional[StateStore] = None):
        self._jobs: Dict[str, JobRecord] = {}
        self._ttl = timedelta(hours=ttl_hours)
        self._lock = threading.Lock()
        self._state_store = state_store
        if self._state_store is not None:
            self._load_from_state()

    def _record_to_json(self, rec: JobRecord) -> Dict[str, Any]:
        return {
            "job_id": rec.job_id,
            "ticker": rec.ticker,
            "date": rec.date,
            "status": rec.status,
            "created_at": rec.created_at.isoformat() + "Z",
            "result": rec.result,
            "error": rec.error,
            "config_snapshot": rec.config_snapshot,
            "progress_events": rec.progress_events,
            "batch_id": rec.batch_id,
            "cancellation_requested": rec.cancellation_requested,
            "analysts": rec.analysts,
            "resumable": rec.resumable,
            "last_graph_step": rec.last_graph_step,
            "checkpoint_thread_id": rec.checkpoint_thread_id,
        }

    def _json_to_record(self, raw: Dict[str, Any]) -> Optional[JobRecord]:
        try:
            created_raw = str(raw.get("created_at") or "").strip()
            if not created_raw:
                return None
            created_at = datetime.fromisoformat(created_raw.replace("Z", ""))
            return JobRecord(
                job_id=str(raw.get("job_id") or "").strip(),
                ticker=str(raw.get("ticker") or "").strip(),
                date=str(raw.get("date") or "").strip(),
                status=str(raw.get("status") or "queued"),
                created_at=created_at,
                result=raw.get("result") if isinstance(raw.get("result"), dict) else None,
                error=str(raw.get("error")) if raw.get("error") is not None else None,
                config_snapshot=raw.get("config_snapshot")
                if isinstance(raw.get("config_snapshot"), dict)
                else {},
                progress_events=raw.get("progress_events")
                if isinstance(raw.get("progress_events"), list)
                else [],
                batch_id=str(raw.get("batch_id")).strip()
                if raw.get("batch_id") is not None
                else None,
                cancellation_requested=bool(raw.get("cancellation_requested")),
                analysts=[
                    str(a).strip()
                    for a in (raw.get("analysts") or [])
                    if str(a).strip()
                ],
                resumable=bool(raw.get("resumable")),
                last_graph_step=int(raw["last_graph_step"])
                if raw.get("last_graph_step") is not None
                else None,
                checkpoint_thread_id=str(raw.get("checkpoint_thread_id")).strip()
                if raw.get("checkpoint_thread_id")
                else None,
            )
        except Exception:
            return None

    def _persist_locked(self, job_id: str, *, touch_index: bool = False) -> None:
        if self._state_store is None:
            return
        rec = self._jobs.get(job_id)
        if rec is None:
            return
        try:
            self._state_store.put_json(
                f"{_JOBS_PERSIST_PREFIX}{job_id}",
                self._record_to_json(rec),
            )
            if touch_index:
                ids = self._state_store.get_json(_JOBS_PERSIST_INDEX_KEY) or []
                if not isinstance(ids, list):
                    ids = []
                new_ids = [job_id] + [str(x) for x in ids if str(x) != job_id]
                self._state_store.put_json(
                    _JOBS_PERSIST_INDEX_KEY,
                    new_ids[:_MAX_PERSISTED_JOB_IDS],
                )
        except Exception:
            logger.exception("Could not persist job snapshot for %s", job_id)

    def _load_from_state(self) -> None:
        assert self._state_store is not None
        try:
            ids = self._state_store.get_json(_JOBS_PERSIST_INDEX_KEY) or []
            if not isinstance(ids, list):
                return
            loaded = 0
            for raw_id in ids[:_MAX_PERSISTED_JOB_IDS]:
                job_id = str(raw_id).strip()
                if not job_id:
                    continue
                payload = self._state_store.get_json(f"{_JOBS_PERSIST_PREFIX}{job_id}")
                if not isinstance(payload, dict):
                    continue
                rec = self._json_to_record(payload)
                if rec is None or not rec.job_id:
                    continue
                if rec.status in ("queued", "running"):
                    rec.status = "failed"
                    _refresh_checkpoint_metadata(rec)
                    if rec.resumable:
                        rec.error = (
                            rec.error
                            or (
                                f"Service restarted with checkpoint at step "
                                f"{rec.last_graph_step}. Use Resume to continue."
                            )
                        )
                    else:
                        rec.error = (
                            rec.error
                            or "Service restarted before this job finished."
                        )
                    rec.progress_events.append(
                        {
                            "ts": datetime.utcnow().isoformat() + "Z",
                            "stage": "failed",
                            "message": rec.error or "Service restarted before this job finished.",
                        }
                    )
                self._jobs[rec.job_id] = rec
                loaded += 1
            if loaded:
                logger.info("Restored %d jobs from state store", loaded)
            self._prune()
        except Exception:
            logger.exception("Could not restore persisted jobs from state store")

    def create(
        self,
        ticker: str,
        date: str,
        config: Dict[str, Any],
        *,
        batch_id: Optional[str] = None,
        analysts: Optional[list] = None,
    ) -> str:
        job_id = str(uuid.uuid4())[:8]
        selected = _coerce_analyst_ids(analysts)
        with self._lock:
            self._jobs[job_id] = JobRecord(
                job_id=job_id,
                ticker=ticker,
                date=date,
                status="queued",
                created_at=datetime.utcnow(),
                config_snapshot={k: v for k, v in config.items() if "key" not in k.lower()},
                batch_id=batch_id,
                analysts=selected,
            )
            self._persist_locked(job_id, touch_index=True)
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
            analysts=list(rec.analysts),
            resumable=rec.resumable,
            last_graph_step=rec.last_graph_step,
            checkpoint_thread_id=rec.checkpoint_thread_id,
        )

    def update_status(self, job_id: str, status: str) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec:
                rec.status = status
                self._persist_locked(job_id)

    def set_result(self, job_id: str, result: Dict[str, Any]) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec:
                rec.status = "completed"
                rec.result = result
                rec.resumable = False
                rec.last_graph_step = None
                rec.checkpoint_thread_id = None
                self._persist_locked(job_id)

    def set_error(self, job_id: str, error: str) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec:
                rec.status = "failed"
                rec.error = error
                _refresh_checkpoint_metadata(rec)
                self._persist_locked(job_id)

    def refresh_checkpoint_metadata(self, job_id: str) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec:
                _refresh_checkpoint_metadata(rec)
                self._persist_locked(job_id)

    def prepare_resume(self, job_id: str) -> Optional[JobRecord]:
        """Mark a failed resumable job as queued again. Returns snapshot or None."""
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec is None:
                return None
            _refresh_checkpoint_metadata(rec)
            if rec.status != "failed" or not rec.resumable:
                return None
            step = rec.last_graph_step
            rec.status = "queued"
            rec.error = None
            rec.cancellation_requested = False
            rec.progress_events.append(
                {
                    "ts": datetime.utcnow().isoformat() + "Z",
                    "stage": "queued",
                    "message": (
                        f"Resuming from LangGraph checkpoint"
                        + (f" (step {step})" if step is not None else "")
                        + "…"
                    ),
                }
            )
            self._persist_locked(job_id)
            return self._snapshot_record(rec)

    def request_cancellation(self, job_id: str) -> bool:
        with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return False
            rec.cancellation_requested = True
            self._persist_locked(job_id)
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
                self._persist_locked(job_id)

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
            self._persist_locked(job_id)

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

    def clear(
        self,
        *,
        clear_memory: bool = True,
        clear_persisted: bool = False,
    ) -> int:
        """Clear in-memory jobs and/or persisted snapshots/index."""
        with self._lock:
            removed = 0
            if clear_memory:
                removed = len(self._jobs)
                self._jobs.clear()
            if clear_persisted and self._state_store is not None:
                try:
                    ids = self._state_store.get_json(_JOBS_PERSIST_INDEX_KEY) or []
                    if isinstance(ids, list):
                        for raw_id in ids[:_MAX_PERSISTED_JOB_IDS]:
                            jid = str(raw_id).strip()
                            if jid:
                                # No delete API in StateStore; clear payload and drop index.
                                self._state_store.put_json(
                                    f"{_JOBS_PERSIST_PREFIX}{jid}",
                                    None,
                                )
                    self._state_store.put_json(_JOBS_PERSIST_INDEX_KEY, [])
                except Exception:
                    logger.exception("Could not clear persisted jobs")
            return removed

    def _prune(self) -> None:
        cutoff = datetime.utcnow() - self._ttl
        with self._lock:
            stale = [jid for jid, rec in self._jobs.items() if rec.created_at < cutoff]
            for jid in stale:
                self._jobs.pop(jid, None)
            if self._state_store is not None:
                try:
                    ids = self._state_store.get_json(_JOBS_PERSIST_INDEX_KEY) or []
                    if isinstance(ids, list):
                        alive = set(self._jobs.keys())
                        new_ids = [
                            str(x) for x in ids if str(x) in alive
                        ][:_MAX_PERSISTED_JOB_IDS]
                        old_ids = [str(x) for x in ids][:_MAX_PERSISTED_JOB_IDS]
                        if new_ids != old_ids:
                            self._state_store.put_json(_JOBS_PERSIST_INDEX_KEY, new_ids)
                except Exception:
                    logger.exception("Could not update persisted jobs index during prune")


class Worker:
    """Runs TradingAgentsGraph.propagate under a concurrency semaphore."""

    def __init__(
        self,
        max_concurrency: int = 3,
        ttl_hours: int = 24,
        state_store: Optional[StateStore] = None,
    ):
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.store = JobStore(ttl_hours=ttl_hours, state_store=state_store)

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
        cfg = dict(config)
        if os.environ.get("TRADINGAGENTS_CHECKPOINT_ENABLED") is None:
            cfg.setdefault("checkpoint_enabled", True)
        job_id = self.store.create(
            ticker, date, cfg, batch_id=batch_id, analysts=analysts
        )
        self.store.append_progress(
            job_id, f"Job {job_id} queued for {ticker} @ {date}", stage="queued"
        )
        asyncio.create_task(
            self._run(job_id, ticker, date, cfg, analysts, resumed=False)
        )
        return job_id

    async def resume(self, job_id: str) -> str:
        """Re-queue a failed job that has a LangGraph checkpoint on disk."""
        prepared = self.store.prepare_resume(job_id)
        if prepared is None:
            rec = self.store.get(job_id)
            if rec is None:
                raise ValueError("Job not found")
            if rec.status != "failed":
                raise ValueError(f"Job status is {rec.status!r}, not failed")
            raise ValueError("No LangGraph checkpoint available to resume this job")
        asyncio.create_task(
            self._run(
                job_id,
                prepared.ticker,
                prepared.date,
                prepared.config_snapshot,
                prepared.analysts or None,
                resumed=True,
            )
        )
        return job_id

    async def _run(
        self,
        job_id: str,
        ticker: str,
        date: str,
        config: Dict[str, Any],
        analysts: Optional[list],
        *,
        resumed: bool = False,
    ) -> None:
        async with self.semaphore:
            self.store.update_status(job_id, "running")
            selected_analysts = _coerce_analyst_ids(analysts)
            if resumed:
                step_hint = self.store.get(job_id)
                step = step_hint.last_graph_step if step_hint else None
                self.store.append_progress(
                    job_id,
                    "Resuming multi-agent pipeline from saved LangGraph checkpoint…",
                    stage="running",
                )
                if step is not None:
                    self.store.append_progress(
                        job_id,
                        f"Checkpoint step {step} — completed nodes will be skipped.",
                        stage="running",
                    )
            else:
                self.store.append_progress(
                    job_id,
                    "Starting multi-agent analysis pipeline (analysts → research → trader → risk → PM)…",
                    stage="running",
                )
            self.store.append_progress(
                job_id,
                f"Parallel analyst nodes: {', '.join(selected_analysts)}",
                stage="running",
            )
            self.store.append_progress(
                job_id,
                _runtime_summary(config),
                stage="running",
            )
            try:
                loop = asyncio.get_running_loop()
                self.store.append_progress(
                    job_id,
                    "Running LangGraph propagate(): debates and tool calls "
                    "(hold tight — often several minutes on local / remote LLMs)…",
                    stage="running",
                )
                stop_hb = asyncio.Event()

                async def _heartbeat() -> None:
                    start = time.monotonic()
                    provider = str(config.get("llm_provider") or "unknown")
                    routing_short = _format_data_routing(config)
                    while True:
                        try:
                            await asyncio.wait_for(stop_hb.wait(), timeout=45.0)
                            break
                        except asyncio.TimeoutError:
                            elapsed = int(time.monotonic() - start)
                            hints: list[str] = []
                            if provider == "openrouter":
                                hints.append("OpenRouter free-tier can be slower.")
                            if provider in ("ollama", "ollama-remote"):
                                hints.append(
                                    "Local/remote Ollama throughput varies with model size."
                                )
                            hint_tail = (" " + " ".join(hints)) if hints else ""
                            self.store.append_progress(
                                job_id,
                                f"Still in LangGraph (~{elapsed}s elapsed): LLM nodes + analyst "
                                f"market-data tools ({routing_short}).{hint_tail}",
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
                    selected_analysts=selected_analysts,
                )

                # --- Dimensions post-pass (failure-isolated) ---
                dimensions_enabled = bool(config.get("dimensions_enabled", True))
                dimensions_in_graph_cfg = bool(config.get("dimensions_in_graph", True))
                graph_json_raw = (final_state.get("dimensions_snapshot_json") or "").strip()
                graph_dims: Optional[Dict[str, Any]] = None
                if graph_json_raw:
                    try:
                        graph_dims = json.loads(graph_json_raw)
                    except json.JSONDecodeError:
                        graph_dims = None

                reuse_snapshot = (
                    dimensions_enabled
                    and dimensions_in_graph_cfg
                    and graph_dims is not None
                )

                if dimensions_enabled and not self.store.is_cancellation_requested(job_id):
                    try:
                        from tradingagents.llm_clients import create_llm_client
                        from api.dimensions.schemas import StockDimensions

                        llm_client = create_llm_client(
                            provider=config.get("llm_provider", "openai"),
                            model=config.get("quick_think_llm", "gpt-4o-mini"),
                            base_url=config.get("backend_url"),
                        )
                        llm = llm_client.get_llm()

                        validated: Optional[StockDimensions] = None
                        if reuse_snapshot:
                            try:
                                validated = StockDimensions.model_validate(graph_dims)
                                if validated is not None and _should_rebuild_graph_dimensions_snapshot(
                                    validated.model_dump(mode="python")
                                ):
                                    validated = None
                            except Exception as exc:
                                logger.warning(
                                    "Invalid graph dimensions snapshot; rebuilding: %s", exc
                                )
                                validated = None

                        if validated is not None:
                            self.store.append_progress(
                                job_id,
                                "Dimensions: reusing LangGraph snapshot (commentary only)…",
                                stage="dimensions",
                            )
                            result["dimensions"] = validated.model_dump()
                            if not self.store.is_cancellation_requested(job_id):
                                self.store.append_progress(
                                    job_id,
                                    "Building dimensions: writing commentary (1 LLM call)…",
                                    stage="dimensions",
                                )
                                commentary = await loop.run_in_executor(
                                    None,
                                    lambda: build_commentary(
                                        dimensions=validated,
                                        pm_decision_text=final_state.get("final_trade_decision") or "",
                                        llm=llm,
                                    ),
                                )
                                result["dimensions_commentary"] = commentary.model_dump()
                            self.store.append_progress(
                                job_id,
                                f"Dimensions reused (version {validated.dimensions_version}). Persisting…",
                                stage="dimensions",
                            )
                        else:
                            self.store.append_progress(
                                job_id,
                                "Building dimensions: extracting quantitative inputs "
                                "(same routed market-data tools as analysts)…",
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
                            result["dimensions"] = dimensions.model_dump()
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
                            self.store.append_progress(
                                job_id,
                                f"Dimensions built (version {dimensions.dimensions_version}). Persisting…",
                                stage="dimensions",
                            )
                    except DimensionsBuildError as exc:
                        _apply_dimensions_failure(result, exc, job_id=job_id)
                        stage = (
                            "dimensions_commentary_skipped"
                            if result.get("dimensions")
                            else "dimensions_skipped"
                        )
                        self.store.append_progress(
                            job_id, f"Dimensions skipped: {exc}",
                            stage=stage,
                        )
                    except Exception as exc:
                        logger.exception("Unexpected dimensions failure for %s", job_id)
                        _apply_dimensions_failure(result, exc, job_id=job_id)
                        stage = (
                            "dimensions_commentary_skipped"
                            if result.get("dimensions")
                            else "dimensions_skipped"
                        )
                        self.store.append_progress(
                            job_id, f"Dimensions skipped: {exc}",
                            stage=stage,
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
                        snap = dict(done.config_snapshot)
                        if done.analysts:
                            snap["analysts"] = list(done.analysts)
                        persist_completed_run(
                            get_state_store(),
                            job_id=job_id,
                            ticker=ticker,
                            date=date,
                            result=result,
                            created_at=done.created_at,
                            batch_id=done.batch_id,
                            config_snapshot=snap,
                        )
                except Exception:
                    logger.exception("History persistence failed for job %s", job_id)
                    raise
                self.store.append_progress(
                    job_id,
                    f"Completed. Rating: {rating}",
                    stage="completed",
                )
                logger.info("Job %s completed for %s", job_id, ticker)
            except Exception as exc:
                logger.exception("Job %s failed for %s", job_id, ticker)
                self.store.set_error(job_id, f"{type(exc).__name__}: {exc}")
                rec_after = self.store.get(job_id)
                resume_hint = ""
                if rec_after and rec_after.resumable:
                    resume_hint = (
                        f" Checkpoint saved at step {rec_after.last_graph_step}; "
                        "use Resume to continue without restarting from scratch."
                    )
                self.store.append_progress(
                    job_id,
                    f"Failed: {type(exc).__name__}: {exc}{resume_hint}",
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
        # The real Kronos forecast runs outside the graph (spec D1, D5);
        # strip the LLM scenario node so it never runs.
        selected = [a for a in selected if a != "kronos"]

        # ---- 1. Compute Kronos forecast (if enabled) -----------------------
        kcfg = KronosConfig.from_env()
        kronos_md = ""
        kronos_payload = None
        kronos_status: str = KronosStatus.ok.value

        if not kcfg.enabled:
            kronos_status = KronosStatus.disabled.value
        else:
            try:
                ohlcv_df = fetch_ohlcv(ticker, date, lookback=kcfg.lookback)
                kronos_payload = KronosService.get(kcfg).forecast(
                    ohlcv_df, ticker=ticker, trade_date=date,
                )
                kronos_md = forecast_to_markdown(kronos_payload)
            except InsufficientData as e:
                logger.warning("kronos: insufficient data for %s: %s", ticker, e)
                kronos_md = (
                    f"_Kronos forecast skipped for {ticker} on {date}: "
                    f"insufficient OHLCV history._"
                )
                kronos_status = KronosStatus.insufficient_data.value
            except ModelLoadError as e:
                logger.warning("kronos: model load failed: %s", e)
                kronos_status = KronosStatus.load_failed.value
            except KronosDisabled:
                kronos_status = KronosStatus.disabled.value
            except Exception as e:  # pragma: no cover - last-resort
                logger.warning("kronos: forecast failed: %s", e, exc_info=True)
                kronos_status = KronosStatus.predict_failed.value

        # ---- 2. Run the graph with a seeded kronos_report ------------------
        with _propagate_sync_lock:
            graph = TradingAgentsGraph(
                selected_analysts=selected,
                config=config,
                debug=False,
            )

            propagator = getattr(graph, "propagator", None)
            if propagator is None or not hasattr(
                propagator, "create_initial_state"
            ):
                # Test fakes / minimal graphs without a propagator — skip
                # the seed and just propagate. kronos_report seeding is a
                # best-effort optimization, not a correctness requirement.
                out = graph.propagate(ticker, date)
            else:
                original_create = propagator.create_initial_state
                had_instance_attr = (
                    "create_initial_state" in propagator.__dict__
                )

                def _seeded_create_initial_state(
                    company_name, trade_date, past_context=""
                ):
                    state = original_create(
                        company_name, trade_date, past_context=past_context,
                    )
                    state["kronos_report"] = kronos_md
                    return state

                propagator.create_initial_state = _seeded_create_initial_state
                try:
                    out = graph.propagate(ticker, date)
                finally:
                    if had_instance_attr:
                        propagator.create_initial_state = original_create
                    else:
                        # No prior instance attribute — remove the patch so
                        # the class-level descriptor takes over again
                        # unchanged.
                        try:
                            del propagator.create_initial_state
                        except AttributeError:
                            propagator.create_initial_state = original_create

        # ---- 3. Merge structured Kronos fields into the final state --------
        final_state, rating = out
        if isinstance(final_state, dict):
            final_state["kronos_forecast"] = forecast_to_state(kronos_payload)
            final_state["kronos_status"] = kronos_status

        logger.info(
            "propagate() finished | ticker=%s kronos_status=%s",
            ticker, kronos_status,
        )
        return (final_state, rating)


# Global singleton instantiated in api.main startup
worker: Optional[Worker] = None
