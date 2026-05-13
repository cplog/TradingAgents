"""FastAPI application for the TradingAgents headless service."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse

from api.config import build_service_config, get_redacted_config, validate_api_key
from api.jobs import Worker
from api.models import AnalyzeRequest, AnalyzeResponse, JobStatusResponse
from api.tickers import normalize_ticker, validate_date

logger = logging.getLogger(__name__)

# Global state managed by lifespan
_service_config: Dict[str, Any] = {}
_worker: Worker | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load config and validate secrets. Shutdown: drain running jobs."""
    global _service_config, _worker

    _service_config = build_service_config()
    validate_api_key(_service_config)

    max_concurrency = _service_config.get("max_concurrency", 3)
    _worker = Worker(max_concurrency=max_concurrency)

    logger.info(
        "TradingAgents API started | provider=%s | deep=%s | quick=%s | concurrency=%d",
        _service_config.get("llm_provider"),
        _service_config.get("deep_think_llm"),
        _service_config.get("quick_think_llm"),
        max_concurrency,
    )
    yield

    # Graceful shutdown: wait up to 60s for running jobs
    if _worker:
        logger.info("Draining running jobs...")
        for _ in range(60):
            running = sum(
                1 for j in _worker.store._jobs.values() if j.status == "running"
            )
            if running == 0:
                break
            await __import__("asyncio").sleep(1)
        logger.info("Shutdown complete.")


app = FastAPI(
    title="TradingAgents API",
    description="Multi-agent LLM financial trading analysis service",
    version="0.2.4",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"


@app.get("/config")
async def get_config() -> Dict[str, Any]:
    """Return the resolved service configuration (API keys redacted)."""
    return get_redacted_config(_service_config)


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Submit a ticker for analysis. Returns immediately with a job id."""
    if not request.ticker:
        raise HTTPException(status_code=400, detail="ticker is required")

    # Normalize ticker (US vs HK)
    try:
        ticker = normalize_ticker(request.ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {exc}")

    # Date defaults to today
    analysis_date = request.date or datetime.utcnow().strftime("%Y-%m-%d")
    if not validate_date(analysis_date):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    # Merge request overrides onto service config
    config = {**_service_config, **(request.config_overrides or {})}

    # Enqueue
    job_id = await _worker.submit(
        ticker=ticker,
        date=analysis_date,
        config=config,
        analysts=request.analysts,
    )

    return AnalyzeResponse(
        job_id=job_id,
        status="queued",
        created_at=datetime.utcnow(),
    )


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str) -> JobStatusResponse:
    """Poll for job status and results."""
    record = _worker.store.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=record.job_id,
        status=record.status,
        created_at=record.created_at,
        result=record.result,
        error=record.error,
    )


@app.get("/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    """Server-Sent Events stream of progress log lines."""

    async def event_gen():
        rec0 = _worker.store.get(job_id)
        if rec0 is None:
            yield "retry: 5000\n"
            yield f"data: {json.dumps({'type': 'error', 'detail': 'Job not found'})}\n\n"
            return

        yield "retry: 5000\n"
        yield (
            "data: "
            + json.dumps({
                "type": "connected",
                "cursor": len(rec0.progress_events),
                "status": rec0.status,
            })
            + "\n\n"
        )

        cursor = len(rec0.progress_events)
        while True:
            chunk, new_cursor, _ = _worker.store.read_progress_since(job_id, cursor)
            cursor = new_cursor
            for evt in chunk:
                yield f"data: {json.dumps(evt)}\n\n"
            rec = _worker.store.get(job_id)
            if rec and rec.status in ("completed", "failed", "cancelled"):
                yield f"data: {json.dumps({'type': 'terminal', 'status': rec.status})}\n\n"
                break
            if rec is None:
                yield f"data: {json.dumps({'type': 'error', 'detail': 'Job not found'})}\n\n"
                break
            await asyncio.sleep(0.35)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.get("/jobs/{job_id}/report")
async def get_report(job_id: str) -> FileResponse:
    """Download the markdown report artifact for a completed job."""
    record = _worker.store.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")
    if record.status != "completed":
        raise HTTPException(
            status_code=409, detail=f"Job is {record.status}; report not ready"
        )

    artifacts_path = record.result.get("artifacts_path") if record.result else None
    if not artifacts_path or not Path(artifacts_path).exists():
        raise HTTPException(status_code=404, detail="Report artifact not found")

    return FileResponse(
        path=artifacts_path,
        media_type="text/markdown",
        filename=f"{record.ticker}_{record.date}_report.md",
    )
