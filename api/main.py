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

from pydantic import BaseModel, Field

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
    list_history_coverage,
    list_runs,
    persist_completed_run,
)
from api.dimensions.builder import (
    DimensionsBuildError,
    build_commentary as build_commentary_orchestrator,
    build_dimensions,
    build_dimensions_facts_only,
)
from api.dimensions.schemas import DimensionsCommentary, StockDimensions
from api.models import (
    AnalysisResult,
    AnalyzeRequest,
    AnalyzeResponse,
    BatchAnalyzeRequest,
    BatchAnalyzeResponse,
    BatchStatusResponse,
    DataSourceCheck,
    HealthResponse,
    HistoryCompareRequest,
    HistoryCompareResponse,
    HistoryCoverageRow,
    IndustryConstituentRow,
    HistoryRunDetail,
    HistoryRunRef,
    JobDimensionsResponse,
    JobStatusResponse,
    RuntimeConfigUpdateRequest,
)
from api.news import fetch_news_feed
from api.state_store import ALLOWED_PERSISTED_SECRET_KEYS, get_state_store

logger = logging.getLogger(__name__)

# Global state managed by lifespan
_service_config: Dict[str, Any] = {}
_worker: Worker | None = None
_data_source_health_cache: Dict[str, DataSourceCheck] = {}
_data_source_health_cached_at: Optional[datetime] = None

STATE_SERVICE_OVERRIDES = "service_overrides"
STATE_PERSISTED_SECRETS = "persisted_secrets"


class PeerCacheRefreshRequest(BaseModel):
    """Admin payload for documenting a peer-universe intent (full warm stays CLI-first)."""

    sector: str
    industry: Optional[str] = None
    tickers: List[str] = Field(default_factory=list)
    mode: str = Field(
        default="global",
        description="global | local | sector — matches scripts/warm_peer_cache.py",
    )
    exchange: Optional[str] = None
    currency: Optional[str] = None


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


def _utc_iso_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _check_yfinance() -> DataSourceCheck:
    now = _utc_iso_now()
    try:
        import yfinance as yf

        data = yf.Ticker("AAPL").history(period="1d")
        if data is None or data.empty:
            return DataSourceCheck(
                ok=False,
                configured=True,
                checked_at=now,
                detail="yfinance returned empty data",
            )
        return DataSourceCheck(ok=True, configured=True, checked_at=now)
    except Exception as exc:
        return DataSourceCheck(
            ok=False,
            configured=True,
            checked_at=now,
            detail=str(exc),
        )


def _check_finnhub() -> DataSourceCheck:
    now = _utc_iso_now()
    token = os.getenv("FINNHUB_API_KEY", "").strip()
    if not token:
        return DataSourceCheck(
            ok=False,
            configured=False,
            checked_at=now,
            detail="FINNHUB_API_KEY not set",
        )
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": "AAPL", "token": token},
            timeout=8,
        )
        if r.status_code == 429:
            return DataSourceCheck(
                ok=False,
                configured=True,
                checked_at=now,
                detail="rate limited (429)",
            )
        if r.status_code >= 400:
            return DataSourceCheck(
                ok=False,
                configured=True,
                checked_at=now,
                detail=f"HTTP {r.status_code}",
            )
        payload = r.json()
        price = payload.get("c")
        ok = isinstance(price, (int, float))
        return DataSourceCheck(
            ok=ok,
            configured=True,
            checked_at=now,
            detail=None if ok else "missing quote price in response",
        )
    except Exception as exc:
        return DataSourceCheck(
            ok=False,
            configured=True,
            checked_at=now,
            detail=str(exc),
        )


def _check_alpha_vantage() -> DataSourceCheck:
    now = _utc_iso_now()
    token = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
    if not token:
        return DataSourceCheck(
            ok=False,
            configured=False,
            checked_at=now,
            detail="ALPHA_VANTAGE_API_KEY not set",
        )
    try:
        r = requests.get(
            "https://www.alphavantage.co/query",
            params={"function": "GLOBAL_QUOTE", "symbol": "IBM", "apikey": token},
            timeout=8,
        )
        if r.status_code == 429:
            return DataSourceCheck(
                ok=False,
                configured=True,
                checked_at=now,
                detail="rate limited (429)",
            )
        if r.status_code >= 400:
            return DataSourceCheck(
                ok=False,
                configured=True,
                checked_at=now,
                detail=f"HTTP {r.status_code}",
            )
        payload = r.json()
        if isinstance(payload, dict):
            if payload.get("Note"):
                return DataSourceCheck(
                    ok=False,
                    configured=True,
                    checked_at=now,
                    detail="rate limited (Note)",
                )
            quote = payload.get("Global Quote")
            if isinstance(quote, dict) and quote.get("05. price"):
                return DataSourceCheck(ok=True, configured=True, checked_at=now)
        return DataSourceCheck(
            ok=False,
            configured=True,
            checked_at=now,
            detail="unexpected response shape",
        )
    except Exception as exc:
        return DataSourceCheck(
            ok=False,
            configured=True,
            checked_at=now,
            detail=str(exc),
        )


def _check_google_rss() -> DataSourceCheck:
    now = _utc_iso_now()
    try:
        r = requests.get(
            "https://news.google.com/rss/search",
            params={"q": "AAPL stock", "hl": "en", "gl": "US", "ceid": "US:en"},
            headers={"User-Agent": "TradingAgents/healthcheck"},
            timeout=8,
        )
        if r.status_code >= 400:
            return DataSourceCheck(
                ok=False,
                configured=True,
                checked_at=now,
                detail=f"HTTP {r.status_code}",
            )
        body = r.text.lstrip()
        ok = "<rss" in body[:400] or body.startswith("<?xml")
        return DataSourceCheck(
            ok=ok,
            configured=True,
            checked_at=now,
            detail=None if ok else "non-RSS response",
        )
    except Exception as exc:
        return DataSourceCheck(
            ok=False,
            configured=True,
            checked_at=now,
            detail=str(exc),
        )


def _check_akshare() -> DataSourceCheck:
    now = _utc_iso_now()
    try:
        import akshare as ak  # type: ignore[import-untyped]

        # Lightweight probe: metadata-style endpoint, avoids large dataframe pulls.
        symbols = ak.stock_us_famous_spot_em()
        if symbols is None or getattr(symbols, "empty", True):
            return DataSourceCheck(
                ok=False,
                configured=True,
                checked_at=now,
                detail="akshare returned empty dataset",
            )
        return DataSourceCheck(ok=True, configured=True, checked_at=now)
    except ImportError:
        return DataSourceCheck(
            ok=False,
            configured=False,
            checked_at=now,
            detail="akshare package not installed",
        )
    except Exception as exc:
        return DataSourceCheck(
            ok=False,
            configured=True,
            checked_at=now,
            detail=str(exc),
        )


def _check_baostock() -> DataSourceCheck:
    now = _utc_iso_now()
    try:
        import baostock as bs  # type: ignore[import-untyped]

        lg = bs.login()
        if lg.error_code != "0":
            return DataSourceCheck(
                ok=False,
                configured=True,
                checked_at=now,
                detail=f"login failed: {lg.error_msg}",
            )
        bs.logout()
        return DataSourceCheck(ok=True, configured=True, checked_at=now)
    except ImportError:
        return DataSourceCheck(
            ok=False,
            configured=False,
            checked_at=now,
            detail="baostock package not installed",
        )
    except Exception as exc:
        return DataSourceCheck(
            ok=False,
            configured=True,
            checked_at=now,
            detail=str(exc),
        )


def _build_data_source_checks() -> Dict[str, DataSourceCheck]:
    return {
        "yfinance": _check_yfinance(),
        "finnhub": _check_finnhub(),
        "alpha_vantage": _check_alpha_vantage(),
        "google_rss": _check_google_rss(),
        "akshare": _check_akshare(),
        "baostock": _check_baostock(),
    }


def _get_data_source_checks_cached(ttl_seconds: int = 180) -> Dict[str, DataSourceCheck]:
    global _data_source_health_cached_at, _data_source_health_cache
    now = datetime.utcnow()
    if (
        _data_source_health_cached_at is None
        or (now - _data_source_health_cached_at).total_seconds() > ttl_seconds
        or not _data_source_health_cache
    ):
        _data_source_health_cache = _build_data_source_checks()
        _data_source_health_cached_at = now
    return _data_source_health_cache


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
    _worker = Worker(
        max_concurrency=max_concurrency,
        ttl_hours=ttl_hours,
        state_store=get_state_store(),
    )

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
    source_checks = _get_data_source_checks_cached()
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
        data_source_checks=source_checks,
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


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> Dict[str, Any]:
    """Request cooperative cancellation before the worker reaches the next graph boundary."""
    if _worker is None:
        raise HTTPException(status_code=503, detail="Worker not initialized")
    if not _worker.store.request_cancellation(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"cancellation_requested": True}


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


def _job_dimensions_from_result(result: Optional[Dict[str, Any]]) -> JobDimensionsResponse:
    """Parse dimensions + commentary from a completed job's raw result dict."""
    if not result:
        return JobDimensionsResponse()
    raw_d = result.get("dimensions")
    raw_c = result.get("dimensions_commentary")
    err = result.get("dimensions_error")
    dimensions = None
    commentary = None
    if isinstance(raw_d, dict):
        try:
            dimensions = StockDimensions.model_validate(raw_d)
        except Exception:
            dimensions = None
    if isinstance(raw_c, dict):
        try:
            commentary = DimensionsCommentary.model_validate(raw_c)
        except Exception:
            commentary = None
    err_str: Optional[str] = None
    if err is not None and str(err).strip():
        err_str = str(err).strip()
    return JobDimensionsResponse(dimensions=dimensions, commentary=commentary, error=err_str)


@app.get("/jobs/{job_id}/dimensions", response_model=JobDimensionsResponse)
async def get_job_dimensions(job_id: str) -> JobDimensionsResponse:
    record = _worker.store.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")
    if record.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Job is {record.status}; dimensions are available when the job completes",
        )
    return _job_dimensions_from_result(record.result)


@app.get("/dimensions/{ticker}", response_model=StockDimensions)
@app.get("/api/dimensions/{ticker}", response_model=StockDimensions)
async def get_dimensions_preview(
    ticker: str,
    as_of_date: Optional[str] = Query(
        None,
        description="YYYY-MM-DD (optional); defaults to today UTC",
    ),
) -> StockDimensions:
    """Facts-only dimensions snapshot for screening (no analyst reports, no LLM)."""
    from api.tickers import normalize_ticker, validate_date

    try:
        sym = normalize_ticker(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {exc}")

    day = (as_of_date or "").strip() or datetime.utcnow().strftime("%Y-%m-%d")
    if not validate_date(day):
        raise HTTPException(status_code=400, detail="as_of_date must be YYYY-MM-DD")

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            None,
            lambda: build_dimensions_facts_only(
                ticker=sym, as_of_date=day, config=_service_config
            ),
        )
    except DimensionsBuildError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/history/runs", response_model=List[HistoryRunRef])
async def history_list_runs(
    ticker: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    sector: Optional[str] = Query(
        None,
        description="Filter by dimensions facts sector (requires D1-backed history).",
    ),
    industry: Optional[str] = Query(
        None,
        description="Filter by dimensions facts industry (requires D1-backed history).",
    ),
) -> List[HistoryRunRef]:
    """List persisted analysis runs from state store (newest-first per index)."""
    from api.tickers import validate_date

    sect = sector.strip() if sector and sector.strip() else None
    ind = industry.strip() if industry and industry.strip() else None

    if (sect or ind) and not d1_history_enabled():
        raise HTTPException(
            status_code=501,
            detail=(
                "sector/industry filters require Cloudflare D1 history "
                "(CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_D1_DATABASE_ID, CLOUDFLARE_API_TOKEN)."
            ),
        )

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
        sector=sect,
        industry=ind,
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


@app.get("/api/history/coverage", response_model=List[HistoryCoverageRow])
async def history_sector_industry_coverage() -> List[HistoryCoverageRow]:
    """Sector/industry run counts aggregated from persisted dimensions facts (D1 only)."""
    try:
        raw = list_history_coverage()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return [HistoryCoverageRow.model_validate(r) for r in raw]


@app.get("/api/catalog/industry-constituents", response_model=List[IndustryConstituentRow])
@app.get("/api/history/constituents", response_model=List[IndustryConstituentRow])
async def history_industry_constituents(
    sector: str = Query(..., min_length=1),
    industry: str = Query(..., min_length=1),
    market: Optional[str] = Query(None, description="US, HK, or omit for all markets"),
) -> List[IndustryConstituentRow]:
    """Catalog constituents for a sector/industry bucket with per-ticker analysis coverage.

    Exposed at ``/api/catalog/industry-constituents`` (preferred) and ``/api/history/constituents`` (legacy).
    """
    from api.dimensions.sector_industry_catalog import list_industry_constituents

    try:
        raw = list_industry_constituents(sector, industry, market=market)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return [IndustryConstituentRow.model_validate(r) for r in raw]


@app.get("/api/history/runs/{run_id}", response_model=HistoryRunDetail)
async def history_get_run(run_id: str) -> HistoryRunDetail:
    raw = get_run(get_state_store(), run_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Run not found")
    return HistoryRunDetail.model_validate(raw)


@app.delete("/api/history/runs/{run_id}")
async def history_delete_run(run_id: str) -> Dict[str, Any]:
    rid = run_id.strip()
    if not rid:
        raise HTTPException(status_code=400, detail="run_id is required")
    deleted = delete_run(get_state_store(), rid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"deleted": True, "run_id": rid}


@app.post("/api/history/compare", response_model=HistoryCompareResponse)
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


@app.post("/api/history/runs/{run_id}/recompute-dimensions", response_model=HistoryRunDetail)
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


@app.post("/admin/jobs/clear")
async def clear_jobs_admin(
    body: Optional[Dict[str, Any]] = None,
    _admin: None = Depends(_admin_key_dep),
) -> Dict[str, Any]:
    """Clear API job state in memory and/or persisted snapshots."""
    if _worker is None:
        raise HTTPException(status_code=503, detail="Worker not initialized")
    mode = str((body or {}).get("mode", "all")).strip().lower()
    if mode not in ("memory", "persisted", "all"):
        raise HTTPException(
            status_code=400,
            detail="mode must be one of: memory, persisted, all",
        )
    if mode == "memory":
        removed = _worker.store.clear(clear_memory=True, clear_persisted=False)
    elif mode == "persisted":
        _worker.store.clear(clear_memory=False, clear_persisted=True)
        removed = 0
    else:
        removed = _worker.store.clear(clear_memory=True, clear_persisted=True)
    return {"cleared": True, "mode": mode, "jobs_removed": removed}


@app.post("/admin/dimensions/peer-cache/refresh")
async def refresh_peer_cache_admin(
    body: PeerCacheRefreshRequest,
    _admin: None = Depends(_admin_key_dep),
) -> Dict[str, Any]:
    """Accept peer-universe parameters for operators; full cache build remains CLI-first.

    Use ``scripts/warm_peer_cache.py`` to materialize JSON + optional D1 rows.
    """
    return {
        "status": "accepted",
        "tickers_written": 0,
        "message": (
            "Peer cache warming is intentionally manual: run scripts/warm_peer_cache.py "
            "`global`, `local`, or `sector` with a ticker list. When Cloudflare D1 is "
            "configured with TRADINGAGENTS_ADMIN_KEY, warmed universes still mirror "
            "through that script unless --no-d1 is passed."
        ),
        "request": body.model_dump(),
    }


# --- Static SPA (production build) ---
if FRONTEND_DIST.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIST), html=True),
        name="spa",
    )
