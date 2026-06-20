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
    MAX_HISTORY_RUNS_QUERY_LIMIT,
    compare_runs,
    compute_sector_analytics,
    d1_history_enabled,
    delete_all_runs,
    delete_run,
    delete_runs,
    get_run,
    list_blooming_industries,
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
    CatalogStatusResponse,
    DataSourceCheck,
    DEFAULT_ANALYST_ORDER,
    HealthResponse,
    HistoryCompareRequest,
    HistoryCompareResponse,
    HistoryBulkDeleteRequest,
    HistoryBulkDeleteResponse,
    HistoryDeleteAllRequest,
    HistoryCoverageRow,
    IndustryConstituentRow,
    HistoryRunDetail,
    HistoryRunRef,
    JobDimensionsResponse,
    JobLiveContextResponse,
    JobStatusResponse,
    MonitorTickerRequest,
    MonitorWatchlistSetRequest,
    NotificationConfig,
    NotificationStatus,
    NotificationTestRequest,
    ResumeJobResponse,
    RuntimeConfigUpdateRequest,
    SCAN_MODE_ANALYSTS,
    SectorAnalyticsResponse,
)
from api.news import fetch_news_feed
from api.notifications import get_manager, reset_manager_for_tests
from api.state_store import ALLOWED_PERSISTED_SECRET_KEYS, get_state_store
from api.topics_models import TopicSearchRequest, TopicUpdateRequest
from api.hpm import compute_hpm_score, HPMScoreResult, should_gate_analysis

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
    from api.models import RunProvenance
    from api.run_provenance import build_run_provenance

    result_model: Optional[AnalysisResult] = None
    cov_raw: Optional[dict] = None
    if rec.result:
        try:
            result_model = AnalysisResult.model_validate(rec.result)
            if isinstance(rec.result, dict):
                raw_cov = rec.result.get("analyst_coverage")
                cov_raw = raw_cov if isinstance(raw_cov, dict) else None
        except Exception:
            result_model = None
    prov_raw = build_run_provenance(rec.config_snapshot, cov_raw)
    provenance = RunProvenance.model_validate(prov_raw) if prov_raw else None
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
        resumable=bool(rec.resumable),
        last_graph_step=rec.last_graph_step,
        checkpoint_thread_id=rec.checkpoint_thread_id,
        provenance=provenance,
        trigger=rec.trigger,
        signal_score=rec.signal_score,
        analysts=list(rec.analysts or []),
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


def _check_kronos() -> DataSourceCheck:
    """Lightweight Kronos readiness (no HF weight download on health)."""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        from api.kronos.config import KronosConfig

        kcfg = KronosConfig.from_env()
    except Exception as exc:
        return DataSourceCheck(
            ok=False,
            configured=True,
            checked_at=now,
            detail=f"kronos config error: {exc}",
        )
    if not kcfg.enabled:
        return DataSourceCheck(
            ok=True,
            configured=False,
            checked_at=now,
            detail="KRONOS_ENABLED=false",
        )
    try:
        import torch  # noqa: F401
    except ImportError:
        return DataSourceCheck(
            ok=False,
            configured=True,
            checked_at=now,
            detail=(
                "torch not installed in this Python environment — activate the "
                "same venv/conda as uvicorn, then run scripts/dev_up.sh"
            ),
        )
    vendor = Path(__file__).resolve().parents[1] / "vendor" / "kronos"
    if not (vendor / "model" / "kronos.py").is_file():
        return DataSourceCheck(
            ok=False,
            configured=True,
            checked_at=now,
            detail="vendor/kronos missing — run scripts/dev_up.sh",
        )
    import sys

    sp = str(vendor)
    if sp not in sys.path:
        sys.path.insert(0, sp)
    try:
        from model import Kronos, KronosTokenizer  # type: ignore  # noqa: F401
    except Exception as exc:
        return DataSourceCheck(
            ok=False,
            configured=True,
            checked_at=now,
            detail=f"vendored Kronos import failed: {exc}",
        )
    return DataSourceCheck(
        ok=True,
        configured=True,
        checked_at=now,
        detail=f"ready (device={kcfg.resolved_device}, model={kcfg.model})",
    )


def _build_data_source_checks() -> Dict[str, DataSourceCheck]:
    return {
        "yfinance": _check_yfinance(),
        "finnhub": _check_finnhub(),
        "alpha_vantage": _check_alpha_vantage(),
        "google_rss": _check_google_rss(),
        "akshare": _check_akshare(),
        "baostock": _check_baostock(),
        "kronos": _check_kronos(),
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
    try:
        validate_api_key(_service_config)
    except RuntimeError:
        logger.warning(
            "API key for provider '%s' is not set — configure via admin or set the env var before submitting jobs.",
            _service_config.get("llm_provider", "unknown"),
        )

    max_concurrency = int(_service_config.get("max_concurrency", 3))
    ttl_hours = int(_service_config.get("job_ttl_hours", 24))
    _worker = Worker(
        max_concurrency=max_concurrency,
        ttl_hours=ttl_hours,
        state_store=get_state_store(),
    )
    restarted = await _worker.restart_queued_jobs()

    # Prime notification manager so /api/health reports accurate status.
    get_manager()

    from api.history import warmup_history_storage

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, warmup_history_storage)
        logger.info("History storage warmup complete")
    except Exception:
        logger.exception("History storage warmup failed (first list query may retry DDL)")

    logger.info(
        "TradingAgents API started | provider=%s | deep=%s | quick=%s | concurrency=%d | restarted_jobs=%d",
        _service_config.get("llm_provider"),
        _service_config.get("deep_think_llm"),
        _service_config.get("quick_think_llm"),
        max_concurrency,
        restarted,
    )

    from api.monitor.engine import get_monitor_engine

    monitor = get_monitor_engine(
        worker=_worker,
        service_config=_service_config,
        state_store=get_state_store(),
    )
    if bool(_service_config.get("monitor_enabled")) and monitor is not None:
        await monitor.start()
        logger.info("Overnight monitor background loop started")

    from api.topics import get_topics_engine

    topics = get_topics_engine(
        service_config=_service_config,
        state_store=get_state_store(),
    )
    if topics is not None:
        await topics.start()
        logger.info("Topics background scheduler started (60s loop)")

    yield

    if topics is not None:
        await topics.stop()

    if monitor is not None:
        await monitor.stop()

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
        supported_analyst_ids=list(DEFAULT_ANALYST_ORDER),
        notifications=get_manager().status().model_dump(mode="json"),
    )


@app.get("/api/notifications", response_model=NotificationConfig)
async def get_notifications_config() -> NotificationConfig:
    return get_manager().get_config()


@app.put("/api/notifications", response_model=NotificationConfig)
async def put_notifications_config(config: NotificationConfig) -> NotificationConfig:
    get_manager().put_config(config)
    return get_manager().get_config()


@app.post("/api/notifications/test")
async def test_notification_channel(req: NotificationTestRequest) -> dict:
    return await get_manager().test_channel(req.channel_id, req.message)


@app.get("/api/notifications/status", response_model=NotificationStatus)
async def get_notifications_status() -> NotificationStatus:
    return get_manager().status()


@app.post("/analyze", response_model=AnalyzeResponse)
@app.post("/api/analyze", response_model=AnalyzeResponse)
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

    analysts = request.analysts

    # --- HPM regime pre-filter (Phase 1) ---
    regime_snapshot = None
    if config.get("regime_prefilter_enabled"):
        regime = compute_hpm_score()
        regime_snapshot = regime.model_dump(mode="json")
        mode = config.get("regime_prefilter_mode", "observe")
        if mode == "observe":
            logger.info(
                "HPM observe: composite=%s posture=%s for ticker=%s",
                regime.composite_score,
                regime.trading_posture,
                ticker,
            )
        elif mode == "enforce" and should_gate_analysis(regime.composite_score, config):
            logger.warning(
                "HPM enforce: gating analysis for ticker=%s (composite=%s < threshold=%s)",
                ticker,
                regime.composite_score,
                config.get("regime_enforce_threshold", 2.5),
            )
            # Tighten policy: reduce debate rounds, limit analysts to scan mode
            config = {
                **config,
                "max_debate_rounds": max(0, int(config.get("max_debate_rounds", 1)) - 1),
                "max_risk_discuss_rounds": max(0, int(config.get("max_risk_discuss_rounds", 1)) - 1),
            }
            if analysts is None:
                analysts = list(SCAN_MODE_ANALYSTS)
        # Attach snapshot to config so downstream nodes can access it
        config["_regime_snapshot"] = regime_snapshot

    trigger: Optional[str] = None
    overnight_signal = request.overnight_signal
    if request.mode == "scan":
        trigger = "scan"
        if analysts is None:
            analysts = list(SCAN_MODE_ANALYSTS)
        config = {
            **config,
            "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1,
        }

    if request.report_format:
        config = {**config, "report_format": request.report_format}

    job_id = await _worker.submit(
        ticker=ticker,
        date=analysis_date,
        config=config,
        analysts=analysts,
        trigger=trigger,
        overnight_signal=overnight_signal,
    )

    return AnalyzeResponse(
        job_id=job_id,
        status="queued",
        created_at=datetime.utcnow(),
    )


@app.post("/batches", response_model=BatchAnalyzeResponse)
@app.post("/api/batches", response_model=BatchAnalyzeResponse)
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
    if request.report_format:
        base_config = {**base_config, "report_format": request.report_format}
    try:
        validate_api_key(base_config)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # --- HPM regime pre-filter (Phase 1) ---
    regime_snapshot = None
    if base_config.get("regime_prefilter_enabled"):
        regime = compute_hpm_score()
        regime_snapshot = regime.model_dump(mode="json")
        mode = base_config.get("regime_prefilter_mode", "observe")
        if mode == "observe":
            logger.info(
                "HPM observe (batch): composite=%s posture=%s batch=%s",
                regime.composite_score,
                regime.trading_posture,
                batch_id,
            )
        elif mode == "enforce" and should_gate_analysis(regime.composite_score, base_config):
            logger.warning(
                "HPM enforce (batch): gating batch=%s (composite=%s < threshold=%s)",
                batch_id,
                regime.composite_score,
                base_config.get("regime_enforce_threshold", 2.5),
            )
            # Tighten policy for every job in the batch
            base_config = {
                **base_config,
                "max_debate_rounds": max(0, int(base_config.get("max_debate_rounds", 1)) - 1),
                "max_risk_discuss_rounds": max(0, int(base_config.get("max_risk_discuss_rounds", 1)) - 1),
            }
            if request.analysts is None:
                request.analysts = list(SCAN_MODE_ANALYSTS)
        base_config["_regime_snapshot"] = regime_snapshot

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
@app.get("/api/jobs", response_model=List[JobStatusResponse])
async def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
) -> List[JobStatusResponse]:
    """List recent jobs ordered by creation time (newest first)."""
    snapshots = [_worker.store.get(jid) for jid in _worker.store.list_ids()]
    records = [r for r in snapshots if r is not None]
    records.sort(key=lambda r: r.created_at, reverse=True)
    out: List[JobStatusResponse] = []
    for rec in records[:limit]:
        if status is None or rec.status == status:
            out.append(_record_to_status(rec))
    return out


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str) -> JobStatusResponse:
    record = _worker.store.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")
    return _record_to_status(record)


def _monitor_engine():
    from api.monitor.engine import get_monitor_engine

    eng = get_monitor_engine()
    if eng is None:
        raise HTTPException(status_code=503, detail="Monitor not initialized")
    return eng


@app.get("/api/monitor/status")
async def monitor_status() -> Dict[str, Any]:
    """Overnight monitor session state and last poll snapshot."""
    return _monitor_engine().status()


@app.get("/api/monitor/watchlist")
async def monitor_get_watchlist() -> Dict[str, Any]:
    eng = _monitor_engine()
    return {"tickers": eng.watchlist.list_tickers()}


@app.put("/api/monitor/watchlist")
async def monitor_set_watchlist(body: MonitorWatchlistSetRequest) -> Dict[str, Any]:
    eng = _monitor_engine()
    tickers = eng.watchlist.set_tickers(body.tickers)
    return {"tickers": tickers}


@app.post("/api/monitor/watchlist")
async def monitor_add_watchlist(body: MonitorTickerRequest) -> Dict[str, Any]:
    from api.tickers import normalize_ticker

    try:
        sym = normalize_ticker(body.ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    eng = _monitor_engine()
    tickers = eng.watchlist.add(sym)
    return {"tickers": tickers}


@app.delete("/api/monitor/watchlist/{ticker}")
async def monitor_remove_watchlist(ticker: str) -> Dict[str, Any]:
    eng = _monitor_engine()
    tickers = eng.watchlist.remove(ticker)
    return {"tickers": tickers}


@app.get("/api/monitor/signals")
async def monitor_list_signals(limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
    eng = _monitor_engine()
    return {"signals": eng.watchlist.list_signals(limit=limit)}


@app.post("/api/monitor/tick")
async def monitor_tick() -> Dict[str, Any]:
    """Run one monitor poll immediately (manual trigger)."""
    eng = _monitor_engine()
    return await eng.tick_once()


def _topics_engine():
    from api.topics import get_topics_engine

    eng = get_topics_engine()
    if eng is None:
        raise HTTPException(status_code=503, detail="Topics engine not initialized")
    return eng


def _topics_store():
    from api.topics_store import get_topics_store

    return get_topics_store(get_state_store())


@app.get("/api/hpm/score")
async def hpm_score(
    index: str = Query("SPY", min_length=1, description="Reference index ticker"),
) -> Dict[str, Any]:
    """Return current deterministic HPM regime snapshot.

    Readonly endpoint independent from the job pipeline.
    """
    result = compute_hpm_score(index.strip().upper())
    return result.model_dump(mode="json")


@app.get("/api/topics")
@app.get("/topics")
async def topics_list() -> Dict[str, Any]:
    from api.topics_models import TopicListResponse

    summaries = _topics_store().list_summaries()
    return TopicListResponse(topics=summaries).model_dump(mode="json")


@app.get("/api/topics/{topic_id}")
@app.get("/topics/{topic_id}")
async def topics_get(topic_id: str) -> Dict[str, Any]:
    from api.topics_models import TopicDetailResponse

    store = _topics_store()
    topic = store.get_topic(topic_id.strip())
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    latest = store.latest_run(topic.id)
    return TopicDetailResponse(topic=topic, latest_run=latest).model_dump(mode="json")


@app.get("/api/topics/{topic_id}/runs")
@app.get("/topics/{topic_id}/runs")
async def topics_runs(topic_id: str) -> Dict[str, Any]:
    from api.topics_models import TopicRunsResponse

    store = _topics_store()
    if store.get_topic(topic_id.strip()) is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    runs = store.list_runs(topic_id.strip())
    return TopicRunsResponse(runs=runs).model_dump(mode="json")


@app.post("/api/topics/search")
@app.post("/topics/search")
async def topics_search(body: TopicSearchRequest) -> Dict[str, Any]:
    from api.topics import TopicsBudgetExceeded
    from api.topics_models import TopicDetailResponse

    q = body.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail="query is required")
    eng = _topics_engine()
    try:
        topic, run = await eng.search_and_run(q, label=body.label, cadence=body.cadence)
    except TopicsBudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return TopicDetailResponse(topic=topic, latest_run=run).model_dump(mode="json")


@app.post("/api/topics/{topic_id}/refresh")
@app.post("/topics/{topic_id}/refresh")
async def topics_refresh(topic_id: str) -> Dict[str, Any]:
    from api.topics import TopicsBudgetExceeded, TopicsRefreshCooldown
    from api.topics_models import TopicRefreshResponse

    eng = _topics_engine()
    if _topics_store().get_topic(topic_id.strip()) is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    try:
        run = await eng.refresh_topic(topic_id.strip())
    except TopicsRefreshCooldown as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except TopicsBudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return TopicRefreshResponse(run=run).model_dump(mode="json")


@app.patch("/api/topics/{topic_id}")
@app.patch("/topics/{topic_id}")
async def topics_patch(topic_id: str, body: TopicUpdateRequest) -> Dict[str, Any]:
    from api.topics_models import TopicDetailResponse
    from api.topics_store import _utc_now_iso

    store = _topics_store()
    topic = store.get_topic(topic_id.strip())
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    if body.label is not None:
        topic.label = body.label.strip() or topic.label
    if body.query is not None:
        q = body.query.strip()
        if not q:
            raise HTTPException(status_code=400, detail="query cannot be empty")
        topic.query = q
    if body.cadence is not None:
        topic.cadence = body.cadence
    topic.updated_at = _utc_now_iso()
    store.save_topic(topic)
    latest = store.latest_run(topic.id)
    return TopicDetailResponse(topic=topic, latest_run=latest).model_dump(mode="json")


@app.post("/api/topics/{topic_id}/pin")
@app.post("/topics/{topic_id}/pin")
async def topics_pin(topic_id: str) -> Dict[str, Any]:
    from api.topics_models import TopicDetailResponse
    from api.topics_store import _utc_now_iso

    store = _topics_store()
    topic = store.get_topic(topic_id.strip())
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    topic.pinned = True
    topic.updated_at = _utc_now_iso()
    store.save_topic(topic)
    latest = store.latest_run(topic.id)
    return TopicDetailResponse(topic=topic, latest_run=latest).model_dump(mode="json")


@app.delete("/api/topics/{topic_id}/pin")
@app.delete("/topics/{topic_id}/pin")
async def topics_unpin(topic_id: str) -> Dict[str, Any]:
    from api.topics_models import TopicDetailResponse
    from api.topics_store import _utc_now_iso

    store = _topics_store()
    topic = store.get_topic(topic_id.strip())
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    topic.pinned = False
    topic.updated_at = _utc_now_iso()
    store.save_topic(topic)
    latest = store.latest_run(topic.id)
    return TopicDetailResponse(topic=topic, latest_run=latest).model_dump(mode="json")


@app.delete("/api/topics/{topic_id}")
@app.delete("/topics/{topic_id}")
async def topics_delete(topic_id: str) -> Dict[str, Any]:
    from api.topics_models import TopicSource

    store = _topics_store()
    topic = store.get_topic(topic_id.strip())
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    if topic.source != TopicSource.user:
        raise HTTPException(status_code=403, detail="Only user-owned topics can be deleted")
    store.delete_topic(topic.id)
    return {"deleted": topic.id}


@app.get("/api/topics/status")
@app.get("/topics/status")
async def topics_status() -> Dict[str, Any]:
    return _topics_engine().status()


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> Dict[str, Any]:
    """Request cooperative cancellation before the worker reaches the next graph boundary."""
    if _worker is None:
        raise HTTPException(status_code=503, detail="Worker not initialized")
    if not _worker.store.request_cancellation(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"cancellation_requested": True}


@app.post("/jobs/cancel-all")
@app.post("/api/jobs/cancel-all")
async def cancel_all_jobs() -> Dict[str, Any]:
    """Stop all queued and running analysis jobs (cooperative for in-flight graphs)."""
    if _worker is None:
        raise HTTPException(status_code=503, detail="Worker not initialized")
    return await _worker.cancel_all_active()


@app.post("/jobs/{job_id}/resume", response_model=ResumeJobResponse)
@app.post("/api/jobs/{job_id}/resume", response_model=ResumeJobResponse)
async def resume_job(job_id: str) -> ResumeJobResponse:
    """Re-queue a failed job and continue from the last LangGraph checkpoint."""
    if _worker is None:
        raise HTTPException(status_code=503, detail="Worker not initialized")
    record = _worker.store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if record.status != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"Job status is {record.status!r}; only failed jobs can be resumed",
        )
    try:
        await _worker.resume(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    refreshed = _worker.store.get(job_id)
    step = refreshed.last_graph_step if refreshed else record.last_graph_step
    return ResumeJobResponse(
        job_id=job_id,
        status="queued",
        resumable=True,
        last_graph_step=step,
        message=(
            f"Job re-queued; LangGraph will resume from checkpoint"
            + (f" step {step}" if step is not None else "")
            + "."
        ),
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


REPORT_FORMAT_MAP: Dict[str, str] = {
    "markdown": ("complete_report.md", "text/markdown", ".md"),
    "json": ("complete_report.json", "application/json", ".json"),
    "structured": ("structured_fields.json", "application/json", ".json"),
}


@app.get("/jobs/{job_id}/report")
async def get_report(job_id: str, format: str = "markdown") -> FileResponse:
    record = _worker.store.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")
    if record.status != "completed":
        raise HTTPException(
            status_code=409, detail=f"Job is {record.status}; report not ready"
        )
    fmt = format if format in REPORT_FORMAT_MAP else "markdown"
    artifact_name, media_type, extension = REPORT_FORMAT_MAP[fmt]
    artifacts_path = record.result.get("artifacts_path") if record.result else None
    if not artifacts_path:
        raise HTTPException(status_code=404, detail="Report artifact path not in job result")
    artifacts_dir = Path(artifacts_path).parent
    artifact_file = artifacts_dir / artifact_name
    if not artifact_file.exists():
        raise HTTPException(status_code=404, detail=f"Report artifact not found: {artifact_name}")
    return FileResponse(
        path=artifact_file,
        media_type=media_type,
        filename=f"{record.ticker}_{record.date}_report{extension}",
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


@app.get("/jobs/{job_id}/live-context", response_model=JobLiveContextResponse)
@app.get("/api/jobs/{job_id}/live-context", response_model=JobLiveContextResponse)
async def get_job_live_context(job_id: str) -> JobLiveContextResponse:
    """Live quote vs entry/stop/target from a completed job's reports."""
    record = _worker.store.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")
    if record.status != "completed" or not record.result:
        raise HTTPException(
            status_code=409,
            detail=f"Job is {record.status}; live context requires a completed report",
        )
    from tradingagents.agents.utils.execution_context import build_live_context_payload

    ticker = str(record.ticker or "").strip()
    trade_date = str(record.date or "").strip()
    reports = record.result.get("reports") if isinstance(record.result, dict) else None
    run_snapshot = (
        record.result.get("live_context_at_run") if isinstance(record.result, dict) else None
    )
    completed_at = (
        record.result.get("completed_at") if isinstance(record.result, dict) else None
    )
    structured = (
        record.result.get("structured") if isinstance(record.result, dict) else None
    )
    plan_levels = (
        record.result.get("plan_levels") if isinstance(record.result, dict) else None
    )
    payload = build_live_context_payload(
        ticker,
        trade_date,
        reports,
        run_snapshot=run_snapshot,
        completed_at=str(completed_at) if completed_at else None,
        structured=structured if isinstance(structured, dict) else None,
        plan_levels=plan_levels if isinstance(plan_levels, dict) else None,
    )
    return JobLiveContextResponse.model_validate(payload)


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
    limit: int = Query(50, ge=1, le=MAX_HISTORY_RUNS_QUERY_LIMIT),
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


@app.get("/api/catalog/status", response_model=CatalogStatusResponse)
async def catalog_status() -> CatalogStatusResponse:
    """Yahoo sector/industry catalog freshness — counts + newest ``updated_at``.

    The frontend surfaces this as a "Catalog refreshed N days ago" pill so users
    can see at a glance whether the weekly refresh job is keeping the universe
    of tickers up to date.
    """
    if not d1_history_enabled():
        return CatalogStatusResponse(d1_enabled=False)

    from api.history import _d1_query, _ensure_d1_schema

    _ensure_d1_schema()

    def _first(rows: list[dict[str, Any]], key: str) -> Any:
        return rows[0].get(key) if rows else None

    buckets_rows = _d1_query(
        "SELECT COUNT(*) AS n, MAX(updated_at) AS m FROM yahoo_sector_industry_buckets"
    )
    cons_rows = _d1_query(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN market = 'US' THEN 1 ELSE 0 END) AS us,
          SUM(CASE WHEN market = 'HK' THEN 1 ELSE 0 END) AS hk,
          MAX(updated_at) AS m
        FROM yahoo_industry_constituents
        """
    )

    def _as_float(val: Any) -> Optional[float]:
        try:
            f = float(val)
            return f if f > 0 else None
        except (TypeError, ValueError):
            return None

    def _as_int(val: Any) -> int:
        try:
            return int(val or 0)
        except (TypeError, ValueError):
            return 0

    return CatalogStatusResponse(
        d1_enabled=True,
        buckets=_as_int(_first(buckets_rows, "n")),
        constituents_total=_as_int(_first(cons_rows, "total")),
        constituents_us=_as_int(_first(cons_rows, "us")),
        constituents_hk=_as_int(_first(cons_rows, "hk")),
        latest_bucket_refreshed_at=_as_float(_first(buckets_rows, "m")),
        latest_constituent_refreshed_at=_as_float(_first(cons_rows, "m")),
    )


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


@app.get("/api/sectors/analytics", response_model=SectorAnalyticsResponse)
async def sector_analytics(
    sector: str = Query(..., min_length=1),
    industry: str = Query(..., min_length=1),
    market: str = Query("ALL", description="US, HK, or ALL"),
) -> SectorAnalyticsResponse:
    """Sector/industry analytics from persisted run data (D1 only)."""
    if not d1_history_enabled():
        raise HTTPException(status_code=501, detail="D1 is not configured")

    from api.dimensions.sector_industry_catalog import list_industry_constituents

    try:
        constituents = list_industry_constituents(sector, industry, market=market if market != "ALL" else None)
    except RuntimeError:
        constituents = []
    total_constituents = len(constituents)

    try:
        raw = compute_sector_analytics(
            sector=sector,
            industry=industry,
            total_constituents=total_constituents,
        )
    except RuntimeError as exc:
        msg = str(exc)
        if msg == "d1_not_configured":
            raise HTTPException(status_code=501, detail="D1 is not configured")
        raise HTTPException(status_code=500, detail=msg) from exc

    return SectorAnalyticsResponse.model_validate(raw)


@app.get("/api/sectors/blooming")
async def sector_blooming(
    market: Optional[str] = Query(None, description="US, HK, or omit for all markets"),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict[str, Any]]:
    """Rank industries by bloom/expansion signal across the catalog (D1 only)."""
    if not d1_history_enabled():
        raise HTTPException(status_code=501, detail="D1 is not configured")

    try:
        results = list_blooming_industries(market=market, limit=limit)
    except RuntimeError as exc:
        msg = str(exc)
        if msg == "d1_not_configured":
            raise HTTPException(status_code=501, detail="D1 is not configured")
        raise HTTPException(status_code=500, detail=msg) from exc

    return results


@app.get("/api/history/runs/{run_id}", response_model=HistoryRunDetail)
async def history_get_run(run_id: str) -> HistoryRunDetail:
    from api.models import RunProvenance
    from api.run_provenance import build_run_provenance

    raw = get_run(get_state_store(), run_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Run not found")
    payload = dict(raw)
    cfg = payload.get("config_snapshot")
    cov = payload.get("analyst_coverage")
    if isinstance(cfg, dict):
        payload["provenance"] = build_run_provenance(
            cfg, cov if isinstance(cov, dict) else None
        )
    return HistoryRunDetail.model_validate(payload)


@app.get("/api/history/runs/{run_id}/live-context", response_model=JobLiveContextResponse)
async def history_run_live_context(run_id: str) -> JobLiveContextResponse:
    from tradingagents.agents.utils.execution_context import build_live_context_payload

    raw = get_run(get_state_store(), run_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Run not found")
    ticker = str(raw.get("ticker") or "").strip()
    trade_date = str(raw.get("date") or raw.get("trade_date") or "").strip()
    reports = raw.get("reports") if isinstance(raw.get("reports"), dict) else None
    run_snapshot = raw.get("live_context_at_run") if isinstance(raw, dict) else None
    completed_at = raw.get("completed_at") if isinstance(raw, dict) else None
    structured = raw.get("structured") if isinstance(raw.get("structured"), dict) else None
    plan_levels = raw.get("plan_levels") if isinstance(raw.get("plan_levels"), dict) else None
    payload = build_live_context_payload(
        ticker,
        trade_date,
        reports,
        run_snapshot=run_snapshot,
        completed_at=str(completed_at) if completed_at else None,
        structured=structured,
        plan_levels=plan_levels,
    )
    return JobLiveContextResponse.model_validate(payload)


def _purge_job_after_history_delete(run_id: str) -> bool:
    """Remove in-memory worker job so History list does not resurrect the row."""
    if _worker is None:
        return False
    return _worker.store.remove(run_id)


def _purge_jobs_matching_history_filters(
    *,
    ticker: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> int:
    """Drop worker jobs that match history delete-all filters (in-memory rows)."""
    if _worker is None:
        return 0
    from api.tickers import normalize_ticker

    norm_ticker: Optional[str] = None
    if ticker and ticker.strip():
        try:
            norm_ticker = normalize_ticker(ticker.strip())
        except ValueError:
            return 0
    removed = 0
    for jid in list(_worker.store.list_ids()):
        rec = _worker.store.get(jid)
        if rec is None:
            continue
        if norm_ticker and str(rec.ticker or "").upper() != norm_ticker:
            continue
        d = str(rec.date or "")
        if date_from and d and d < date_from:
            continue
        if date_to and d and d > date_to:
            continue
        if _worker.store.remove(jid):
            removed += 1
    return removed


def _delete_history_runs_with_job_purge(run_ids: List[str]) -> Dict[str, Any]:
    """Delete persisted history and always purge matching in-memory jobs."""
    deleted: List[str] = []
    missing: List[str] = []
    seen: set[str] = set()
    store = get_state_store()
    for raw in run_ids:
        rid = (raw or "").strip()
        if not rid or rid in seen:
            continue
        seen.add(rid)
        hist = delete_run(store, rid)
        job = _purge_job_after_history_delete(rid)
        if hist or job:
            deleted.append(rid)
        else:
            missing.append(rid)
    return {
        "deleted_count": len(deleted),
        "deleted_run_ids": deleted,
        "missing_run_ids": missing,
        "scope": "selected",
    }


@app.delete("/api/history/runs/{run_id}")
async def history_delete_run(run_id: str) -> Dict[str, Any]:
    rid = run_id.strip()
    if not rid:
        raise HTTPException(status_code=400, detail="run_id is required")
    deleted_history = delete_run(get_state_store(), rid)
    removed_job = _purge_job_after_history_delete(rid)
    if not deleted_history and not removed_job:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "deleted": True,
        "run_id": rid,
        "history_deleted": deleted_history,
        "job_removed": removed_job,
    }


@app.post("/api/history/runs/bulk-delete", response_model=HistoryBulkDeleteResponse)
async def history_bulk_delete_runs(body: HistoryBulkDeleteRequest) -> HistoryBulkDeleteResponse:
    """Delete multiple persisted runs by id."""
    ids = [rid.strip() for rid in body.run_ids if rid and rid.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="run_ids must contain at least one id")
    result = _delete_history_runs_with_job_purge(ids)
    return HistoryBulkDeleteResponse.model_validate(result)


@app.post("/api/history/runs/delete-all", response_model=HistoryBulkDeleteResponse)
async def history_delete_all_runs(body: HistoryDeleteAllRequest) -> HistoryBulkDeleteResponse:
    """Delete all runs matching optional filters (omit filters to delete entire history)."""
    from api.tickers import validate_date

    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm must be true")

    sect = body.sector.strip() if body.sector and body.sector.strip() else None
    ind = body.industry.strip() if body.industry and body.industry.strip() else None
    if (sect or ind) and not d1_history_enabled():
        raise HTTPException(
            status_code=501,
            detail=(
                "sector/industry filters require Cloudflare D1 history "
                "(CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_D1_DATABASE_ID, CLOUDFLARE_API_TOKEN)."
            ),
        )
    if body.date_from is not None and not validate_date(body.date_from):
        raise HTTPException(status_code=400, detail="date_from must be YYYY-MM-DD")
    if body.date_to is not None and not validate_date(body.date_to):
        raise HTTPException(status_code=400, detail="date_to must be YYYY-MM-DD")

    ticker_val = body.ticker.strip() if body.ticker and body.ticker.strip() else None
    try:
        result = delete_all_runs(
            get_state_store(),
            ticker=ticker_val,
            date_from=body.date_from,
            date_to=body.date_to,
            sector=sect,
            industry=ind,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    _purge_jobs_matching_history_filters(
        ticker=ticker_val,
        date_from=body.date_from,
        date_to=body.date_to,
    )
    return HistoryBulkDeleteResponse.model_validate(result)


@app.post("/api/history/compare", response_model=HistoryCompareResponse)
async def history_compare(body: HistoryCompareRequest) -> HistoryCompareResponse:
    payload = compare_runs(get_state_store(), body.run_id_a.strip(), body.run_id_b.strip())
    if payload is None:
        raise HTTPException(status_code=404, detail="One or both runs not found")
    return HistoryCompareResponse.model_validate(payload)


def _build_llm_for_dimensions(cfg: Dict[str, Any]):
    """Construct an LLM client suitable for dimensions recomputation.

    Wraps Ollama-served LLMs so `with_structured_output` uses
    `response_format` (json_schema/json_mode) instead of function_calling —
    the function_calling path silently returns None on most Ollama models,
    which forces the dimensions builder to fall back to neutral defaults.
    """
    from tradingagents.llm_clients import create_llm_client
    from api.llm_clients import adapt_for_structured_output

    provider = cfg["llm_provider"]
    client = create_llm_client(
        provider=provider,
        model=cfg["quick_think_llm"],
        base_url=cfg.get("backend_url"),
    )
    return adapt_for_structured_output(client.get_llm(), provider)


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
