"""FastAPI application for the TradingAgents headless service + UX API."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from api.config import (
    REQUIRED_API_KEYS,
    build_service_config,
    get_redacted_config,
    merge_request_config,
    validate_api_key,
)
from api.jobs import Worker
from api.history import (
    compare_runs,
    d1_history_enabled,
    delete_run,
    get_run,
    list_runs,
    persist_completed_run,
)
from api.dimensions.builder import (
    DimensionsBuildError,
    build_commentary as build_commentary_orchestrator,
    build_dimensions,
)
from api.models import (
    AnalysisResult,
    AnalyzeRequest,
    AnalyzeResponse,
    BatchAnalyzeRequest,
    BatchAnalyzeResponse,
    BatchStatusResponse,
    HealthResponse,
    HistoryCompareRequest,
    HistoryCompareResponse,
    HistoryRunDetail,
    HistoryRunRef,
    JobStatusResponse,
    RuntimeConfigUpdateRequest,
)
from api.news import fetch_news_feed
from api.state_store import ALLOWED_PERSISTED_SECRET_KEYS, get_state_store

logger = logging.getLogger(__name__)

# Global state managed by lifespan
_service_config: Dict[str, Any] = {}
_worker: Worker | None = None

STATE_SERVICE_OVERRIDES = "service_overrides"
STATE_PERSISTED_SECRETS = "persisted_secrets"

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def _load_persisted_into_process() -> None:
    """Apply persisted secrets to os.environ and merge overrides into service config."""
    global _service_config
    # Warm singleton store and report backend mode for UI diagnostics.
    store = get_state_store()
    secrets = store.get_json(STATE_PERSISTED_SECRETS) or {}
    if isinstance(secrets, dict):
        for k, v in secrets.items():
            if k in ALLOWED_PERSISTED_SECRET_KEYS and isinstance(v, str):
                os.environ[k] = v
    _service_config = build_service_config()
    overrides = store.get_json(STATE_SERVICE_OVERRIDES) or {}
    if isinstance(overrides, dict):
        _service_config.update(overrides)


def _record_to_status(rec) -> JobStatusResponse:
    """Map JobRecord snapshot to response model."""
    result_model: Optional[AnalysisResult] = None
    if rec.result:
        try:
            result_model = AnalysisResult.model_validate(rec.result)
        except Exception:
            result_model = None
    return JobStatusResponse(
        job_id=rec.job_id,
        status=rec.status,
        created_at=rec.created_at,
        ticker=rec.ticker,
        date=rec.date,
        result=result_model,
        error=rec.error,
        progress_events=list(rec.progress_events or []),
        batch_id=rec.batch_id,
    )


def _normalize_ollama_base(base_url: Optional[str]) -> str:
    raw = (base_url or "").strip()
    if not raw:
        raw = (
            os.getenv("OLLAMA_BASE_URL", "").strip()
            or os.getenv("OLLAMA_CF_URL", "").strip()
            or "http://localhost:11434"
        )
    if raw.endswith("/v1"):
        raw = raw[:-3]
    return raw.rstrip("/")


def _fetch_ollama_models(base_url: Optional[str], provider: str = "ollama") -> Dict[str, Any]:
    base = _normalize_ollama_base(base_url)
    tags_url = f"{base}/api/tags"
    ps_url = f"{base}/api/ps"
    prov = provider.strip().lower()
    headers: dict[str, str] = {}
    if prov == "ollama-remote":
        # Same headers as ChatOpenAI for Cloudflare Access / front-door auth.
        from tradingagents.llm_clients.openai_client import _resolve_ollama_headers

        headers = _resolve_ollama_headers("ollama-remote")
    hdr = headers if headers else None
    try:
        tags_resp = requests.get(tags_url, headers=hdr, timeout=20)
        tags_resp.raise_for_status()
        body = tags_resp.text or ""
        ct = tags_resp.headers.get("content-type", "")
        if "json" not in ct.lower() and body.lstrip()[:1] not in "{[":
            snippet = body[:240].replace("\n", " ")
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Ollama tags URL returned non-JSON (often an HTML login page). "
                    f"url={tags_url!r}. For Cloudflare Zero Trust set OLLAMA_CF_TOKEN "
                    f"(or OLLAMA_CF_CLIENT_ID + OLLAMA_CF_CLIENT_SECRET). "
                    f"Body starts with: {snippet!r}"
                ),
            )
        tags_payload = tags_resp.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch Ollama tags: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Ollama tags returned invalid JSON") from exc

    loaded: set[str] = set()
    try:
        ps_resp = requests.get(ps_url, headers=hdr, timeout=12)
        if ps_resp.ok:
            ps_payload = ps_resp.json()
            for m in (ps_payload.get("models") or []):
                name = str(m.get("name") or "").strip()
                if name:
                    loaded.add(name)
    except Exception:
        # /api/ps is optional for UX enhancement; don't fail model listing.
        pass

    models: list[dict[str, Any]] = []
    for m in (tags_payload.get("models") or []):
        name = str(m.get("name") or "").strip()
        if not name:
            continue
        models.append({
            "id": name,
            "label": name,
            "loaded": name in loaded,
            "is_free": None,
        })
    models.sort(key=lambda x: (not bool(x["loaded"]), x["id"].lower()))
    return {"provider": "ollama", "source": tags_url, "models": models}


def _openrouter_is_free(model: dict[str, Any]) -> bool:
    pricing = model.get("pricing") or {}
    prompt = str(pricing.get("prompt") or "")
    completion = str(pricing.get("completion") or "")
    request = str(pricing.get("request") or "")
    if prompt in {"0", "0.0"} and completion in {"0", "0.0"} and request in {"", "0", "0.0"}:
        return True
    model_id = str(model.get("id") or "").lower()
    return ":free" in model_id


def _fetch_openrouter_models(base_url: Optional[str]) -> Dict[str, Any]:
    token = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="OPENROUTER_API_KEY is not configured")
    base = (base_url or str(_service_config.get("backend_url") or "")).strip() or "https://openrouter.ai/api/v1"
    base = base.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    models_url = f"{base}/models"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(models_url, headers=headers, timeout=25)
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch OpenRouter models: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="OpenRouter models returned invalid JSON") from exc

    out: list[dict[str, Any]] = []
    for m in payload.get("data") or []:
        model_id = str(m.get("id") or "").strip()
        if not model_id:
            continue
        label = str(m.get("name") or model_id)
        out.append({
            "id": model_id,
            "label": label,
            "loaded": None,
            "is_free": _openrouter_is_free(m),
        })
    out.sort(key=lambda x: (not bool(x["is_free"]), x["id"].lower()))
    return {"provider": "openrouter", "source": models_url, "models": out}


def _admin_key_dep(x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key")) -> None:
    expected = os.getenv("TRADINGAGENTS_ADMIN_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API disabled (set TRADINGAGENTS_ADMIN_KEY)")
    if not x_admin_key or x_admin_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load config and validate secrets. Shutdown: drain running jobs."""
    global _service_config, _worker

    _load_persisted_into_process()
    validate_api_key(_service_config)

    max_concurrency = int(_service_config.get("max_concurrency", 3))
    ttl_hours = int(_service_config.get("job_ttl_hours", 24))
    _worker = Worker(max_concurrency=max_concurrency, ttl_hours=ttl_hours)

    logger.info(
        "TradingAgents API started | provider=%s | deep=%s | quick=%s | concurrency=%d",
        _service_config.get("llm_provider"),
        _service_config.get("deep_think_llm"),
        _service_config.get("quick_think_llm"),
        max_concurrency,
    )
    yield

    if _worker:
        logger.info("Draining running jobs...")
        for _ in range(60):
            if _worker.store.running_count() == 0:
                break
            await asyncio.sleep(1)
        logger.info("Shutdown complete.")


app = FastAPI(
    title="TradingAgents API",
    description="Multi-agent LLM financial trading analysis service",
    version="0.3.0",
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


@app.get("/providers/{provider}/models")
async def get_provider_models(
    provider: str,
    backend_url: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """List available models for providers with discoverable catalogs.

    Supported dynamic providers:
    - ollama / ollama-local / ollama-remote: via /api/tags (+ optional /api/ps for loaded markers)
    - openrouter: via /models API (requires OPENROUTER_API_KEY)
    """
    p = provider.strip().lower()
    if p in ("ollama", "ollama-local", "ollama-remote"):
        return _fetch_ollama_models(backend_url, p)
    if p == "openrouter":
        return _fetch_openrouter_models(backend_url)
    raise HTTPException(
        status_code=400,
        detail="Model discovery currently supports ollama (local/remote) and openrouter",
    )


@app.get("/api/health", response_model=HealthResponse)
async def api_health() -> HealthResponse:
    """Structured health for the React dashboard."""
    provider = str(_service_config.get("llm_provider", "openai")).lower()
    env_var = REQUIRED_API_KEYS.get(provider)
    if provider == "ollama-remote":
        key_ok = bool(
            os.getenv("OLLAMA_CF_TOKEN", "").strip()
            or os.getenv("OLLAMA_API_KEY", "").strip()
            or (
                os.getenv("OLLAMA_CF_CLIENT_ID", "").strip()
                and os.getenv("OLLAMA_CF_CLIENT_SECRET", "").strip()
            )
        )
    else:
        key_ok = True if env_var is None else bool(os.getenv(env_var))
    cf = bool(
        os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
        and os.getenv("CLOUDFLARE_KV_NAMESPACE_ID", "").strip()
        and os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    )
    d1 = d1_history_enabled()
    yf_ok: Optional[bool] = None
    try:
        import yfinance as yf  # noqa: F401

        yf_ok = True
    except Exception:
        yf_ok = False
    store = get_state_store()
    if d1 and cf:
        store_kind = "cloudflare_d1+kv"
    elif d1:
        store_kind = "cloudflare_d1"
    elif cf:
        store_kind = "cloudflare_kv"
    else:
        store_kind = "local_file"
    return HealthResponse(
        ok=key_ok,
        llm_provider=provider,
        api_key_configured=key_ok,
        state_store=store_kind,
        cloudflare_kv_configured=cf,
        cloudflare_d1_configured=d1,
        data_cache_dir=str(_service_config.get("data_cache_dir", "")),
        results_dir=str(_service_config.get("results_dir", "")),
        yfinance_reachable=yf_ok,
    )


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Submit a ticker for analysis. Returns immediately with a job id."""
    if not request.ticker:
        raise HTTPException(status_code=400, detail="ticker is required")

    from api.tickers import normalize_ticker, validate_date

    try:
        ticker = normalize_ticker(request.ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {exc}")

    analysis_date = request.date or datetime.utcnow().strftime("%Y-%m-%d")
    if not validate_date(analysis_date):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    config = merge_request_config(_service_config, request.config_overrides)
    try:
        validate_api_key(config)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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


@app.post("/batches", response_model=BatchAnalyzeResponse)
async def create_batch(request: BatchAnalyzeRequest) -> BatchAnalyzeResponse:
    """Submit many tickers; share one batch id for portfolio monitoring."""
    from api.tickers import normalize_ticker, validate_date

    analysis_date = request.date or datetime.utcnow().strftime("%Y-%m-%d")
    if not validate_date(analysis_date):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    batch_id = str(uuid.uuid4())[:12]
    job_ids: List[str] = []
    from copy import deepcopy

    base_config = merge_request_config(_service_config, request.config_overrides)
    try:
        validate_api_key(base_config)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    for raw in request.tickers:
        try:
            ticker = normalize_ticker(raw.strip())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid ticker {raw!r}: {exc}")
        jid = await _worker.submit(
            ticker=ticker,
            date=analysis_date,
            config=deepcopy(base_config),
            analysts=request.analysts,
            batch_id=batch_id,
        )
        job_ids.append(jid)

    get_state_store().put_json(
        f"batch:{batch_id}",
        {"job_ids": job_ids, "date": analysis_date, "created_at": datetime.utcnow().isoformat() + "Z"},
    )

    return BatchAnalyzeResponse(
        batch_id=batch_id,
        job_ids=job_ids,
        status="queued",
        created_at=datetime.utcnow(),
    )


@app.get("/batches/{batch_id}", response_model=BatchStatusResponse)
async def get_batch(batch_id: str) -> BatchStatusResponse:
    jobs = [_record_to_status(r) for r in _worker.store.by_batch(batch_id)]
    if not jobs:
        raise HTTPException(status_code=404, detail="Batch not found or expired")
    summary: Dict[str, int] = {}
    for j in jobs:
        summary[j.status] = summary.get(j.status, 0) + 1
    return BatchStatusResponse(batch_id=batch_id, jobs=jobs, summary=summary)


@app.get("/jobs", response_model=List[JobStatusResponse])
async def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
) -> List[JobStatusResponse]:
    """List recent jobs ordered by creation time (newest first)."""
    all_ids = _worker.store.list_ids()
    out: List[JobStatusResponse] = []
    for jid in sorted(all_ids, reverse=True)[:limit]:
        rec = _worker.store.get(jid)
        if rec and (status is None or rec.status == status):
            out.append(_record_to_status(rec))
    return out


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str) -> JobStatusResponse:
    record = _worker.store.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")
    return _record_to_status(record)


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


@app.get("/history/runs", response_model=List[HistoryRunRef])
async def history_list_runs(
    ticker: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
) -> List[HistoryRunRef]:
    """List persisted analysis runs from state store (newest-first per index)."""
    from api.tickers import validate_date

    if date_from is not None and not validate_date(date_from):
        raise HTTPException(status_code=400, detail="date_from must be YYYY-MM-DD")
    if date_to is not None and not validate_date(date_to):
        raise HTTPException(status_code=400, detail="date_to must be YYYY-MM-DD")
    rows = list_runs(
        get_state_store(),
        ticker=ticker,
        limit=limit,
        date_from=date_from,
        date_to=date_to,
    )
    out: List[HistoryRunRef] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("run_id") or r.get("job_id") or "").strip()
        if not rid:
            continue
        rr = dict(r)
        rr["run_id"] = rid
        try:
            out.append(HistoryRunRef.model_validate(rr))
        except Exception:
            continue
    return out


@app.get("/history/runs/{run_id}", response_model=HistoryRunDetail)
async def history_get_run(run_id: str) -> HistoryRunDetail:
    raw = get_run(get_state_store(), run_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Run not found")
    return HistoryRunDetail.model_validate(raw)


@app.delete("/history/runs/{run_id}")
async def history_delete_run(run_id: str) -> Dict[str, Any]:
    rid = run_id.strip()
    if not rid:
        raise HTTPException(status_code=400, detail="run_id is required")
    deleted = delete_run(get_state_store(), rid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"deleted": True, "run_id": rid}


@app.post("/history/compare", response_model=HistoryCompareResponse)
async def history_compare(body: HistoryCompareRequest) -> HistoryCompareResponse:
    payload = compare_runs(get_state_store(), body.run_id_a.strip(), body.run_id_b.strip())
    if payload is None:
        raise HTTPException(status_code=404, detail="One or both runs not found")
    return HistoryCompareResponse.model_validate(payload)


def _build_llm_for_dimensions(cfg: Dict[str, Any]):
    """Construct an LLM client suitable for dimensions recomputation."""
    from tradingagents.llm_clients import create_llm_client

    client = create_llm_client(
        provider=cfg["llm_provider"],
        model=cfg["quick_think_llm"],
        base_url=cfg.get("backend_url"),
    )
    return client.get_llm()


@app.post("/history/runs/{run_id}/recompute-dimensions", response_model=HistoryRunDetail)
async def recompute_dimensions(run_id: str) -> Dict[str, Any]:
    """Recompute dimensions + commentary for an existing run and patch the record."""
    store = get_state_store()
    rec = get_run(store, run_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Run not found")

    reports = rec.get("reports") or {}
    if not isinstance(reports, dict):
        reports = {}
    missing = [k for k in ("market", "social", "news", "fundamentals") if not reports.get(k)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Run is missing reports required to recompute dimensions: {missing}",
        )

    llm = _build_llm_for_dimensions(_service_config)
    try:
        dims = build_dimensions(
            ticker=rec["ticker"],
            as_of_date=rec["date"],
            analyst_reports={
                "market": reports.get("market") or "",
                "social": reports.get("social") or "",
                "news": reports.get("news") or "",
                "fundamentals": reports.get("fundamentals") or "",
            },
            llm=llm,
            config=_service_config,
        )
        commentary = build_commentary_orchestrator(
            dimensions=dims,
            pm_decision_text=reports.get("portfolio_decision") or "",
            llm=llm,
        )
    except DimensionsBuildError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    rec["dimensions"] = dims.model_dump()
    rec["dimensions_commentary"] = commentary.model_dump()
    rec["dimensions_error"] = None

    created_at_raw = rec.get("created_at") or ""
    try:
        created_dt = (
            datetime.fromisoformat(created_at_raw.replace("Z", ""))
            if created_at_raw
            else datetime.utcnow()
        )
    except ValueError:
        created_dt = datetime.utcnow()

    persist_completed_run(
        store,
        job_id=rec["job_id"],
        ticker=rec["ticker"],
        date=rec["date"],
        result=rec,
        created_at=created_dt,
        batch_id=rec.get("batch_id"),
        config_snapshot=rec.get("config_snapshot"),
    )
    return HistoryRunDetail.model_validate(rec).model_dump()


@app.get("/news/{ticker}")
async def news_feed(
    ticker: str,
    limit: int = Query(50, ge=1, le=200),
    days: int = Query(14, ge=1, le=90),
):
    try:
        return fetch_news_feed(ticker, limit=limit, days=days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("news_feed failed")
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/admin/runtime-config")
async def post_runtime_config(
    body: RuntimeConfigUpdateRequest,
    _admin: None = Depends(_admin_key_dep),
) -> Dict[str, str]:
    """Persist non-secret overrides and optional allow-listed secrets."""
    store = get_state_store()
    global _service_config

    if body.service_overrides:
        cur = store.get_json(STATE_SERVICE_OVERRIDES) or {}
        if not isinstance(cur, dict):
            cur = {}
        cur.update({k: v for k, v in body.service_overrides.items() if v is not None})
        store.put_json(STATE_SERVICE_OVERRIDES, cur)

    if body.secrets:
        sec = store.get_json(STATE_PERSISTED_SECRETS) or {}
        if not isinstance(sec, dict):
            sec = {}
        for k, v in body.secrets.items():
            if k in ALLOWED_PERSISTED_SECRET_KEYS and isinstance(v, str) and v.strip():
                sec[k] = v.strip()
                os.environ[k] = v.strip()
        store.put_json(STATE_PERSISTED_SECRETS, sec)

    _load_persisted_into_process()
    try:
        validate_api_key(_service_config)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}


@app.post("/admin/cache/clear")
async def clear_cache(
    body: Optional[Dict[str, Any]] = None,
    _admin: None = Depends(_admin_key_dep),
) -> Dict[str, Any]:
    """Clear LangGraph SQLite checkpoints under data_cache_dir (danger zone)."""
    mode = (body or {}).get("mode", "checkpoints")
    base = Path(_service_config.get("data_cache_dir", "")).resolve()
    if not base.is_dir():
        return {"cleared": False, "detail": "data_cache_dir missing"}
    cleared = []
    if mode in ("checkpoints", "all"):
        ck = base / "checkpoints"
        if ck.is_dir():
            for p in ck.glob("*.db"):
                try:
                    p.unlink()
                    cleared.append(str(p.name))
                except OSError:
                    pass
    return {"cleared": True, "mode": mode, "files": cleared}


# --- Static SPA (production build) ---
if FRONTEND_DIST.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIST), html=True),
        name="spa",
    )
