"""Durable analysis history.

One history backend per deployment (see ``api/cloudflare_storage``):

- **D1** when ``CLOUDFLARE_D1_DATABASE_ID`` is set — all history reads/writes; errors propagate.
- **KV / local StateStore** when D1 is not set — history blobs + indexes only.
- **Sector/industry catalog** (Yahoo) is never stored in D1/KV.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from api.run_provenance import build_run_provenance, merge_config_snapshot
from api.state_store import StateStore, get_state_store
from api.tickers import _safe_ticker_component, normalize_ticker, validate_date

logger = logging.getLogger(__name__)

KEY_PREFIX_RUN = "history:run:"
KEY_PREFIX_TICKER_INDEX = "history:index:ticker:"
KEY_GLOBAL_INDEX = "history:index:global"

MAX_TICKER_INDEX = 200
MAX_GLOBAL_INDEX = 500
# Upper bound for GET /api/history/runs ``limit`` (stats UI uses 500).
MAX_HISTORY_RUNS_QUERY_LIMIT = 500

_d1_initialized = False
_d1_http_session: Optional[requests.Session] = None

# List views should not pull multi-MB JSON blobs over the D1 HTTP API.
_D1_LIST_COLUMNS = """
    run_id, job_id, ticker, trade_date, rating, confidence,
    completed_at, created_at, batch_id,
    factor_scores_json, facts_sector, facts_industry, provenance_json,
    CASE WHEN dimensions_json IS NOT NULL AND
         trim(COALESCE(dimensions_json, '')) NOT IN ('', '{}', 'null')
         THEN 1 ELSE 0 END AS has_dimensions,
    CASE WHEN dimensions_commentary_json IS NOT NULL AND
         trim(COALESCE(dimensions_commentary_json, '')) NOT IN ('', '{}', 'null')
         THEN 1 ELSE 0 END AS has_commentary
"""


def _d1_config() -> Optional[dict[str, str]]:
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    db_id = os.getenv("CLOUDFLARE_D1_DATABASE_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    if account and db_id and token:
        return {"account": account, "db_id": db_id, "token": token}
    return None


def d1_history_enabled() -> bool:
    """True when history should use Cloudflare D1 as primary backend."""
    from api.cloudflare_storage import cloudflare_d1_enabled

    return cloudflare_d1_enabled() and _d1_config() is not None


def _d1_http() -> requests.Session:
    global _d1_http_session
    if _d1_http_session is None:
        sess = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=8)
        sess.mount("https://", adapter)
        _d1_http_session = sess
    return _d1_http_session


def _d1_query(
    sql: str,
    params: Optional[list[Any]] = None,
    *,
    timeout: Optional[float] = None,
) -> list[dict[str, Any]]:
    cfg = _d1_config()
    if not cfg:
        raise RuntimeError("D1 is not configured")

    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{cfg['account']}/d1/database/{cfg['db_id']}/query"
    )
    body: dict[str, Any] = {"sql": sql}
    if params:
        body["params"] = params
    headers = {
        "Authorization": f"Bearer {cfg['token']}",
        "Content-Type": "application/json",
    }
    if timeout is None:
        timeout = float(os.getenv("TRADINGAGENTS_D1_QUERY_TIMEOUT", "35"))
    resp = _d1_http().post(url, headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    result_rows = payload.get("result") or []
    if not isinstance(result_rows, list) or not result_rows:
        return []
    first = result_rows[0] or {}
    if not first.get("success", False):
        raise RuntimeError(f"D1 query failed: {first}")
    rows = first.get("results") or []
    return rows if isinstance(rows, list) else []


def _ensure_d1_schema() -> None:
    global _d1_initialized
    if _d1_initialized:
        return
    _d1_query(
        """
        CREATE TABLE IF NOT EXISTS analysis_runs (
            run_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            rating TEXT,
            confidence REAL,
            reports_json TEXT NOT NULL,
            structured_json TEXT,
            artifacts_path TEXT,
            completed_at TEXT,
            created_at TEXT,
            batch_id TEXT,
            config_snapshot_json TEXT
        )
        """
    )
    _d1_query(
        "CREATE INDEX IF NOT EXISTS idx_analysis_runs_ticker_date "
        "ON analysis_runs (ticker, trade_date DESC)"
    )
    _d1_query(
        "CREATE INDEX IF NOT EXISTS idx_analysis_runs_completed_at "
        "ON analysis_runs (completed_at DESC)"
    )
    # Idempotent column additions for dimensions persistence.
    # D1 has no `ADD COLUMN IF NOT EXISTS`; wrap each in try/except.
    try:
        _d1_query("ALTER TABLE analysis_runs ADD COLUMN dimensions_json TEXT")
    except Exception:
        pass  # column already exists
    try:
        _d1_query("ALTER TABLE analysis_runs ADD COLUMN dimensions_commentary_json TEXT")
    except Exception:
        pass
    try:
        _d1_query("ALTER TABLE analysis_runs ADD COLUMN dimensions_error TEXT")
    except Exception:
        pass
    for col, typ in (
        ("factor_scores_json", "TEXT"),
        ("facts_sector", "TEXT"),
        ("facts_industry", "TEXT"),
        ("provenance_json", "TEXT"),
    ):
        try:
            _d1_query(f"ALTER TABLE analysis_runs ADD COLUMN {col} {typ}")
        except Exception:
            pass
    _d1_query(
        "CREATE INDEX IF NOT EXISTS idx_analysis_runs_facts_sector "
        "ON analysis_runs (facts_sector)"
    )
    _d1_query(
        "CREATE INDEX IF NOT EXISTS idx_analysis_runs_facts_industry "
        "ON analysis_runs (facts_industry)"
    )
    # Dimensions peer-universe persistence (distinct from peer JSON caches on disk).
    _d1_query(
        """
        CREATE TABLE IF NOT EXISTS dimension_peer_universes (
            slug TEXT PRIMARY KEY,
            scope TEXT NOT NULL,
            exchange TEXT,
            currency TEXT,
            sector TEXT NOT NULL,
            industry TEXT NOT NULL,
            peer_count INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL
        )
        """
    )
    _d1_query(
        "CREATE INDEX IF NOT EXISTS idx_dimension_peer_univ_scope "
        "ON dimension_peer_universes (scope)"
    )
    _d1_query(
        """
        CREATE TABLE IF NOT EXISTS dimension_peer_members (
            slug TEXT NOT NULL,
            ticker TEXT NOT NULL,
            facts_json TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (slug, ticker)
        )
        """
    )
    _d1_query(
        "CREATE INDEX IF NOT EXISTS idx_dimension_peer_members_slug "
        "ON dimension_peer_members (slug)"
    )
    _d1_query(
        """
        CREATE TABLE IF NOT EXISTS yahoo_sector_industry_buckets (
            sector TEXT NOT NULL,
            industry TEXT NOT NULL,
            industry_key TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (sector, industry)
        )
        """
    )
    _d1_query(
        """
        CREATE TABLE IF NOT EXISTS yahoo_industry_constituents (
            sector TEXT NOT NULL,
            industry TEXT NOT NULL,
            industry_key TEXT NOT NULL,
            ticker TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (sector, industry, ticker)
        )
        """
    )
    _d1_query(
        "CREATE INDEX IF NOT EXISTS idx_yahoo_industry_constituents_bucket "
        "ON yahoo_industry_constituents (sector, industry)"
    )
    try:
        _d1_query(
            "ALTER TABLE yahoo_industry_constituents ADD COLUMN market TEXT NOT NULL DEFAULT 'US'"
        )
    except Exception:
        pass
    _d1_query(
        "CREATE INDEX IF NOT EXISTS idx_yahoo_industry_constituents_market "
        "ON yahoo_industry_constituents (market, sector, industry)"
    )
    from tradingagents.dataflows.cache.schema import DATA_CACHE_BOOTSTRAP_DDLS

    for ddl in DATA_CACHE_BOOTSTRAP_DDLS:
        _d1_query(ddl)
    _d1_initialized = True


def _run_key(job_id: str) -> str:
    return f"{KEY_PREFIX_RUN}{job_id}"


def _ticker_index_key(ticker: str) -> str:
    safe = _safe_ticker_component(ticker.strip().upper())
    return f"{KEY_PREFIX_TICKER_INDEX}{safe}"


_FACTOR_SCORE_KEYS = (
    "value",
    "growth",
    "quality",
    "momentum",
    "low_risk",
    "sentiment",
)


def _compact_factor_scores(dimensions: Any) -> Dict[str, float]:
    if not isinstance(dimensions, dict):
        return {}
    fs = dimensions.get("factor_scores")
    if not isinstance(fs, dict):
        return {}
    scores: Dict[str, float] = {}
    for name in _FACTOR_SCORE_KEYS:
        v = fs.get(name)
        if isinstance(v, dict) and v.get("score") is not None:
            try:
                scores[name] = float(v["score"])
            except (TypeError, ValueError):
                continue
    return scores


def _list_index_fields_from_full(full: Dict[str, Any]) -> Dict[str, Any]:
    """Denormalized columns for fast GET /api/history/runs (avoids large JSON in list queries)."""
    dims = full.get("dimensions") if isinstance(full.get("dimensions"), dict) else {}
    facts = dims.get("facts") if isinstance(dims.get("facts"), dict) else {}
    scores = _compact_factor_scores(dims)
    cfg = full.get("config_snapshot") if isinstance(full.get("config_snapshot"), dict) else {}
    cov = full.get("analyst_coverage")
    prov = (
        build_run_provenance(cfg, cov if isinstance(cov, dict) else None)
        if cfg
        else None
    )
    sector = facts.get("sector") if isinstance(facts.get("sector"), str) else ""
    industry = facts.get("industry") if isinstance(facts.get("industry"), str) else ""
    return {
        "factor_scores_json": json.dumps(scores, ensure_ascii=False) if scores else None,
        "facts_sector": sector.strip() or None,
        "facts_industry": industry.strip() or None,
        "provenance_json": json.dumps(prov, ensure_ascii=False) if prov else None,
    }


def _parse_factor_scores_json(raw: Any) -> Dict[str, float]:
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: Dict[str, float] = {}
    for k, v in data.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[str(k)] = float(v)
    return out


def _d1_list_row_to_ref(row: Dict[str, Any]) -> Dict[str, Any]:
    """Build a compact history ref from a slim D1 list row."""
    factor_scores = _parse_factor_scores_json(row.get("factor_scores_json"))
    prov_raw = row.get("provenance_json")
    provenance = None
    if isinstance(prov_raw, str) and prov_raw.strip():
        try:
            provenance = json.loads(prov_raw)
        except json.JSONDecodeError:
            provenance = None
    base: Dict[str, Any] = {
        "run_id": row.get("run_id"),
        "job_id": row.get("job_id"),
        "ticker": row.get("ticker"),
        "date": row.get("trade_date"),
        "rating": row.get("rating"),
        "confidence": row.get("confidence"),
        "completed_at": row.get("completed_at"),
        "created_at": row.get("created_at"),
        "batch_id": row.get("batch_id"),
        "has_dimensions": bool(row.get("has_dimensions")),
        "has_commentary": bool(row.get("has_commentary")),
    }
    if factor_scores:
        base["factor_scores"] = factor_scores
    fs_sec = row.get("facts_sector")
    fs_ind = row.get("facts_industry")
    if isinstance(fs_sec, str) and fs_sec.strip():
        base["facts_sector"] = fs_sec.strip()
    if isinstance(fs_ind, str) and fs_ind.strip():
        base["facts_industry"] = fs_ind.strip()
    if isinstance(provenance, dict):
        base["provenance"] = provenance
    return _ref_from_record(base)


def _ref_from_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Compact entry for index lists (no full reports)."""
    ref: Dict[str, Any] = {
        "run_id": rec.get("run_id") or rec.get("job_id"),
        "job_id": rec.get("job_id"),
        "ticker": rec.get("ticker"),
        "date": rec.get("date"),
        "rating": rec.get("rating"),
        "confidence": rec.get("confidence"),
        "completed_at": rec.get("completed_at"),
        "created_at": rec.get("created_at"),
        "batch_id": rec.get("batch_id"),
    }
    hd = rec.get("has_dimensions")
    hc = rec.get("has_commentary")
    if hd is not None:
        ref["has_dimensions"] = bool(hd)
    if hc is not None:
        ref["has_commentary"] = bool(hc)
    fs_sec = rec.get("facts_sector")
    fs_ind = rec.get("facts_industry")
    if isinstance(fs_sec, str) and fs_sec.strip():
        ref["facts_sector"] = fs_sec.strip()
    if isinstance(fs_ind, str) and fs_ind.strip():
        ref["facts_industry"] = fs_ind.strip()
    if isinstance(rec.get("factor_scores"), dict) and rec["factor_scores"]:
        ref["factor_scores"] = dict(rec["factor_scores"])
    else:
        dims = rec.get("dimensions") or {}
        fs = dims.get("factor_scores") if isinstance(dims, dict) else None
        if isinstance(fs, dict):
            scores: Dict[str, Any] = {}
            for name in _FACTOR_SCORE_KEYS:
                v = fs.get(name)
                if isinstance(v, dict) and v.get("score") is not None:
                    scores[name] = v["score"]
            if scores:
                ref["factor_scores"] = scores
    if rec.get("provenance"):
        ref["provenance"] = rec["provenance"]
    else:
        cfg = rec.get("config_snapshot")
        cov = rec.get("analyst_coverage")
        if isinstance(cfg, dict) and cfg:
            ref["provenance"] = build_run_provenance(
                cfg, cov if isinstance(cov, dict) else None
            )
    return ref


def persist_completed_run(
    store: StateStore,
    *,
    job_id: str,
    ticker: str,
    date: str,
    result: Dict[str, Any],
    created_at: datetime,
    batch_id: Optional[str] = None,
    config_snapshot: Optional[Dict[str, Any]] = None,
) -> None:
    """Write full run to configured backend."""
    try:
        norm_ticker = normalize_ticker(ticker)
    except ValueError as exc:
        logger.warning("History skip: invalid ticker %s: %s", ticker, exc)
        return

    if not validate_date(date):
        logger.warning("History skip: invalid date %s", date)
        return

    created_iso = created_at.isoformat() + "Z" if created_at.tzinfo is None else created_at.isoformat()

    full: Dict[str, Any] = {
        "run_id": job_id,
        "job_id": job_id,
        "ticker": norm_ticker,
        "date": date,
        "rating": result.get("rating"),
        "confidence": result.get("confidence"),
        "reports": result.get("reports") or {},
        "analyst_coverage": result.get("analyst_coverage"),
        "structured": result.get("structured"),
        "artifacts_path": result.get("artifacts_path"),
        "completed_at": result.get("completed_at"),
        "created_at": created_iso,
        "batch_id": batch_id,
        "config_snapshot": merge_config_snapshot(config_snapshot),
        "dimensions": result.get("dimensions"),
        "dimensions_commentary": result.get("dimensions_commentary"),
        "dimensions_error": result.get("dimensions_error"),
        "dimensions_in_graph": result.get("dimensions_in_graph"),
    }

    if d1_history_enabled():
        _persist_d1(full)
        return

    _persist_kv_run_and_indexes(store, full, norm_ticker)


def _persist_kv_run_and_indexes(
    store: StateStore, full: Dict[str, Any], norm_ticker: str
) -> None:
    """Write full run blob + list indexes to KV/local StateStore."""
    job_id = str(full.get("job_id") or full.get("run_id") or "")
    store.put_json(_run_key(job_id), full)
    ref = _ref_from_record(full)
    _prepend_ref(store, _ticker_index_key(norm_ticker), ref, MAX_TICKER_INDEX)
    _prepend_ref(store, KEY_GLOBAL_INDEX, ref, MAX_GLOBAL_INDEX)


def _persist_d1(full: Dict[str, Any]) -> None:
    _ensure_d1_schema()
    list_fields = _list_index_fields_from_full(full)
    _d1_query(
        """
        INSERT INTO analysis_runs (
            run_id, job_id, ticker, trade_date, rating, confidence,
            reports_json, structured_json, artifacts_path,
            completed_at, created_at, batch_id, config_snapshot_json,
            dimensions_json, dimensions_commentary_json, dimensions_error,
            factor_scores_json, facts_sector, facts_industry, provenance_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
            job_id = excluded.job_id,
            ticker = excluded.ticker,
            trade_date = excluded.trade_date,
            rating = excluded.rating,
            confidence = excluded.confidence,
            reports_json = excluded.reports_json,
            structured_json = excluded.structured_json,
            artifacts_path = excluded.artifacts_path,
            completed_at = excluded.completed_at,
            created_at = excluded.created_at,
            batch_id = excluded.batch_id,
            config_snapshot_json = excluded.config_snapshot_json,
            dimensions_json = excluded.dimensions_json,
            dimensions_commentary_json = excluded.dimensions_commentary_json,
            dimensions_error = excluded.dimensions_error,
            factor_scores_json = excluded.factor_scores_json,
            facts_sector = excluded.facts_sector,
            facts_industry = excluded.facts_industry,
            provenance_json = excluded.provenance_json
        """,
        [
            str(full.get("run_id") or ""),
            str(full.get("job_id") or ""),
            str(full.get("ticker") or ""),
            str(full.get("date") or ""),
            full.get("rating"),
            full.get("confidence"),
            json.dumps(full.get("reports") or {}, ensure_ascii=False),
            json.dumps(full.get("structured"), ensure_ascii=False)
            if full.get("structured") is not None
            else None,
            full.get("artifacts_path"),
            full.get("completed_at"),
            full.get("created_at"),
            full.get("batch_id"),
            json.dumps(full.get("config_snapshot") or {}, ensure_ascii=False),
            json.dumps(full.get("dimensions"), ensure_ascii=False)
            if full.get("dimensions") is not None
            else None,
            json.dumps(full.get("dimensions_commentary"), ensure_ascii=False)
            if full.get("dimensions_commentary") is not None
            else None,
            full.get("dimensions_error"),
            list_fields["factor_scores_json"],
            list_fields["facts_sector"],
            list_fields["facts_industry"],
            list_fields["provenance_json"],
        ],
    )


def _prepend_ref(store: StateStore, index_key: str, ref: Dict[str, Any], max_len: int) -> None:
    cur = store.get_json(index_key)
    rows: List[Dict[str, Any]] = cur if isinstance(cur, list) else []
    rid = ref.get("run_id") or ref.get("job_id")
    rows = [r for r in rows if (r.get("run_id") or r.get("job_id")) != rid]
    rows.insert(0, ref)
    store.put_json(index_key, rows[:max_len])


def get_run(store: StateStore, run_id: str) -> Optional[Dict[str, Any]]:
    if d1_history_enabled():
        return _get_run_d1(run_id)
    raw = store.get_json(_run_key(run_id))
    return raw if isinstance(raw, dict) else None


def _get_run_d1(run_id: str) -> Optional[Dict[str, Any]]:
    _ensure_d1_schema()
    rows = _d1_query(
        """
        SELECT run_id, job_id, ticker, trade_date, rating, confidence,
               reports_json, structured_json, artifacts_path,
               completed_at, created_at, batch_id, config_snapshot_json,
               dimensions_json, dimensions_commentary_json, dimensions_error
        FROM analysis_runs
        WHERE run_id = ?
        LIMIT 1
        """,
        [run_id],
    )
    if not rows:
        return None
    return _d1_row_to_full(rows[0])


def _d1_row_to_full(row: Dict[str, Any]) -> Dict[str, Any]:
    reports_raw = row.get("reports_json")
    structured_raw = row.get("structured_json")
    cfg_raw = row.get("config_snapshot_json")
    dims_raw = row.get("dimensions_json")
    dims_comm_raw = row.get("dimensions_commentary_json")
    reports = json.loads(reports_raw) if isinstance(reports_raw, str) and reports_raw else {}
    structured = (
        json.loads(structured_raw)
        if isinstance(structured_raw, str) and structured_raw
        else None
    )
    config_snapshot = json.loads(cfg_raw) if isinstance(cfg_raw, str) and cfg_raw else {}
    dimensions = (
        json.loads(dims_raw) if isinstance(dims_raw, str) and dims_raw else None
    )
    dimensions_commentary = (
        json.loads(dims_comm_raw)
        if isinstance(dims_comm_raw, str) and dims_comm_raw
        else None
    )
    return {
        "run_id": row.get("run_id"),
        "job_id": row.get("job_id"),
        "ticker": row.get("ticker"),
        "date": row.get("trade_date"),
        "rating": row.get("rating"),
        "confidence": row.get("confidence"),
        "reports": reports if isinstance(reports, dict) else {},
        "structured": structured if isinstance(structured, dict) else None,
        "artifacts_path": row.get("artifacts_path"),
        "completed_at": row.get("completed_at"),
        "created_at": row.get("created_at"),
        "batch_id": row.get("batch_id"),
        "config_snapshot": config_snapshot if isinstance(config_snapshot, dict) else {},
        "dimensions": dimensions if isinstance(dimensions, dict) else None,
        "dimensions_commentary": (
            dimensions_commentary if isinstance(dimensions_commentary, dict) else None
        ),
        "dimensions_error": row.get("dimensions_error"),
    }


def _in_date_range(d: str, date_from: Optional[str], date_to: Optional[str]) -> bool:
    if date_from and d < date_from:
        return False
    if date_to and d > date_to:
        return False
    return True


def _list_runs_kv_index(
    store: StateStore,
    *,
    ticker: Optional[str],
    limit: int,
    date_from: Optional[str],
    date_to: Optional[str],
) -> List[Dict[str, Any]]:
    """List runs from KV/local indexes (no sector/industry filter)."""
    if ticker:
        try:
            norm = normalize_ticker(ticker)
        except ValueError:
            return []
        idx_key = _ticker_index_key(norm)
    else:
        idx_key = KEY_GLOBAL_INDEX

    cur = store.get_json(idx_key)
    rows: List[Dict[str, Any]] = cur if isinstance(cur, list) else []
    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        d = str(r.get("date") or "")
        if date_from or date_to:
            if not validate_date(d):
                continue
            if not _in_date_range(d, date_from, date_to):
                continue
        enriched = _enrich_ref_from_store(store, r)
        out.append(enriched)
        if len(out) >= limit:
            break
    return out


def _enrich_ref_from_store(store: StateStore, ref: Dict[str, Any]) -> Dict[str, Any]:
    """Backfill provenance for index rows saved before provenance was indexed."""
    if ref.get("provenance"):
        return ref
    jid = str(ref.get("job_id") or ref.get("run_id") or "").strip()
    if not jid:
        return ref
    full = store.get_json(_run_key(jid))
    if not isinstance(full, dict):
        return ref
    cfg = full.get("config_snapshot")
    cov = full.get("analyst_coverage")
    if isinstance(cfg, dict) and cfg:
        merged = dict(ref)
        merged["provenance"] = build_run_provenance(
            cfg, cov if isinstance(cov, dict) else None
        )
        return merged
    return ref


def list_runs(
    store: StateStore,
    *,
    ticker: Optional[str] = None,
    limit: int = 50,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return compact refs, newest-first."""
    lim = max(1, min(limit, MAX_HISTORY_RUNS_QUERY_LIMIT))
    sect = (sector or "").strip()
    ind = (industry or "").strip()
    if (sect or ind) and not d1_history_enabled():
        raise RuntimeError("sector_industry_filters_require_d1")

    if d1_history_enabled():
        return _list_runs_d1(
            ticker=ticker,
            limit=lim,
            date_from=date_from,
            date_to=date_to,
            sector=sect or None,
            industry=ind or None,
        )

    return _list_runs_kv_index(
        store,
        ticker=ticker,
        limit=lim,
        date_from=date_from,
        date_to=date_to,
    )


def _list_runs_d1(
    *,
    ticker: Optional[str],
    limit: int,
    date_from: Optional[str],
    date_to: Optional[str],
    sector: Optional[str],
    industry: Optional[str],
) -> List[Dict[str, Any]]:
    _ensure_d1_schema()
    where: list[str] = []
    params: list[Any] = []
    if ticker:
        where.append("ticker = ?")
        params.append(normalize_ticker(ticker))
    if date_from:
        where.append("trade_date >= ?")
        params.append(date_from)
    if date_to:
        where.append("trade_date <= ?")
        params.append(date_to)
    if sector:
        where.append(
            "(facts_sector = ? OR json_extract(dimensions_json, '$.facts.sector') = ?)"
        )
        params.extend([sector, sector])
    if industry:
        where.append(
            "(facts_industry = ? OR json_extract(dimensions_json, '$.facts.industry') = ?)"
        )
        params.extend([industry, industry])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"""
        SELECT {_D1_LIST_COLUMNS}
        FROM analysis_runs
        {where_sql}
        ORDER BY completed_at DESC, created_at DESC
        LIMIT ?
    """
    params.append(limit)
    list_timeout = float(os.getenv("TRADINGAGENTS_D1_LIST_TIMEOUT", "20"))
    rows = _d1_query(sql, params, timeout=list_timeout)
    return [_d1_list_row_to_ref(row) for row in rows]


def _list_history_coverage_aggregates() -> List[Dict[str, Any]]:
    """D1 GROUP BY sector/industry from persisted dimensions facts."""
    _ensure_d1_schema()
    sql = """
        SELECT
            COALESCE(
                NULLIF(trim(CAST(json_extract(dimensions_json, '$.facts.sector') AS TEXT)), ''),
                '(unknown)'
            ) AS sector,
            COALESCE(
                NULLIF(trim(CAST(json_extract(dimensions_json, '$.facts.industry') AS TEXT)), ''),
                '(unknown)'
            ) AS industry,
            COUNT(*) AS run_count,
            SUM(CASE WHEN dimensions_json IS NOT NULL AND
                    trim(COALESCE(dimensions_json, '')) NOT IN ('', '{}', 'null')
                THEN 1 ELSE 0 END) AS with_dimensions_count,
            SUM(CASE WHEN dimensions_commentary_json IS NOT NULL AND
                    trim(COALESCE(dimensions_commentary_json, '')) NOT IN ('', '{}', 'null')
                THEN 1 ELSE 0 END) AS with_commentary_count,
            MAX(completed_at) AS latest_completed_at
        FROM analysis_runs
        GROUP BY
            COALESCE(
                NULLIF(trim(CAST(json_extract(dimensions_json, '$.facts.sector') AS TEXT)), ''),
                '(unknown)'
            ),
            COALESCE(
                NULLIF(trim(CAST(json_extract(dimensions_json, '$.facts.industry') AS TEXT)), ''),
                '(unknown)'
            )
        ORDER BY sector, industry
    """
    rows = _d1_query(sql, None)
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "sector": row.get("sector"),
                "industry": row.get("industry"),
                "run_count": int(row.get("run_count") or 0),
                "with_dimensions_count": int(row.get("with_dimensions_count") or 0),
                "with_commentary_count": int(row.get("with_commentary_count") or 0),
                "latest_completed_at": row.get("latest_completed_at"),
            }
        )
    return out


def list_history_coverage() -> List[Dict[str, Any]]:
    """Full Yahoo sector/industry grid merged with D1 aggregates when D1 is configured."""
    from api.dimensions.sector_industry_catalog import (
        load_sector_industry_catalog,
        merge_coverage_with_catalog,
    )

    catalog = load_sector_industry_catalog()
    aggregates = (
        _list_history_coverage_aggregates() if d1_history_enabled() else []
    )

    if not catalog:
        return aggregates
    return merge_coverage_with_catalog(catalog, aggregates)


def build_compare_payload(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Structured side-by-side compare (full reports preserved under each side)."""

    def _side(rec: Dict[str, Any]) -> Dict[str, Any]:
        reps = rec.get("reports") or {}
        if not isinstance(reps, dict):
            reps = {}
        pd = reps.get("portfolio_decision") or ""
        tpm = reps.get("trader_plan") or ""
        excerpt_pm = pd[:1200] if isinstance(pd, str) else ""
        excerpt_trader = tpm[:800] if isinstance(tpm, str) else ""
        return {
            "run_id": rec.get("run_id") or rec.get("job_id"),
            "job_id": rec.get("job_id"),
            "ticker": rec.get("ticker"),
            "date": rec.get("date"),
            "rating": rec.get("rating"),
            "confidence": rec.get("confidence"),
            "completed_at": rec.get("completed_at"),
            "created_at": rec.get("created_at"),
            "config_snapshot": rec.get("config_snapshot") or {},
            "reports": reps,
            "structured": rec.get("structured"),
            "artifacts_path": rec.get("artifacts_path"),
            "excerpt_portfolio_decision": excerpt_pm,
            "excerpt_trader_plan": excerpt_trader,
        }

    return {"a": _side(a), "b": _side(b)}


def compare_runs(store: StateStore, run_id_a: str, run_id_b: str) -> Optional[Dict[str, Any]]:
    ra = get_run(store, run_id_a)
    rb = get_run(store, run_id_b)
    if not ra or not rb:
        return None
    return build_compare_payload(ra, rb)


def _delete_kv_run_record(store: StateStore, run_id: str) -> bool:
    """Remove a run blob and list indexes from KV/local StateStore (legacy path)."""
    rid = (run_id or "").strip()
    if not rid:
        return False
    removed = False
    rec = store.get_json(_run_key(rid))
    if isinstance(rec, dict):
        store.put_json(_run_key(rid), None)
        removed = True
        ticker = rec.get("ticker")
        if isinstance(ticker, str) and ticker.strip():
            try:
                norm_ticker = normalize_ticker(ticker)
            except ValueError:
                norm_ticker = None
            if norm_ticker:
                removed = _remove_ref(store, _ticker_index_key(norm_ticker), rid) or removed
    ticker_guess = _ticker_from_global_index(store, rid)
    if ticker_guess:
        try:
            norm_guess = normalize_ticker(ticker_guess)
        except ValueError:
            norm_guess = None
        if norm_guess:
            removed = _remove_ref(store, _ticker_index_key(norm_guess), rid) or removed
    removed = _remove_ref(store, KEY_GLOBAL_INDEX, rid) or removed
    return removed


def delete_run(store: StateStore, run_id: str) -> bool:
    """Delete a run from history storage and indexes."""
    rid = (run_id or "").strip()
    if not rid:
        return False

    if d1_history_enabled():
        deleted = _delete_run_d1(rid)
        # Clear legacy KV copies from before D1-only persistence.
        kv_deleted = _delete_kv_run_record(store, rid)
        return deleted or kv_deleted

    if _delete_kv_run_record(store, rid):
        return True
    rec = store.get_json(_run_key(rid))
    if isinstance(rec, dict):
        store.put_json(_run_key(rid), None)
        return True
    return False


def _remove_ref(store: StateStore, index_key: str, run_id: str) -> bool:
    cur = store.get_json(index_key)
    rows: List[Dict[str, Any]] = cur if isinstance(cur, list) else []
    filtered = [r for r in rows if (r.get("run_id") or r.get("job_id")) != run_id]
    if len(filtered) == len(rows):
        return False
    store.put_json(index_key, filtered)
    return True


def _ticker_from_global_index(store: StateStore, run_id: str) -> Optional[str]:
    """Resolve ticker for a run id from the global history index (no blob required)."""
    cur = store.get_json(KEY_GLOBAL_INDEX)
    rows: List[Dict[str, Any]] = cur if isinstance(cur, list) else []
    for ref in rows:
        if not isinstance(ref, dict):
            continue
        if (ref.get("run_id") or ref.get("job_id")) != run_id:
            continue
        ticker = ref.get("ticker")
        if isinstance(ticker, str) and ticker.strip():
            return ticker.strip()
    return None


def _delete_run_d1(run_id: str) -> bool:
    _ensure_d1_schema()
    try:
        rows = _d1_query(
            "SELECT run_id FROM analysis_runs WHERE run_id = ? OR job_id = ? LIMIT 1",
            [run_id, run_id],
        )
        if not rows:
            return False
        actual = str(rows[0].get("run_id") or run_id).strip()
        _d1_query("DELETE FROM analysis_runs WHERE run_id = ?", [actual])
        still = _d1_query(
            "SELECT run_id FROM analysis_runs WHERE run_id = ? LIMIT 1",
            [actual],
        )
        return not still
    except Exception:
        logger.exception("D1 delete failed for run_id=%s", run_id)
        return False


def delete_runs(store: StateStore, run_ids: List[str]) -> Dict[str, Any]:
    """Delete many runs by id. Returns deleted and missing id lists."""
    deleted: List[str] = []
    missing: List[str] = []
    seen: set[str] = set()
    for raw in run_ids:
        rid = (raw or "").strip()
        if not rid or rid in seen:
            continue
        seen.add(rid)
        if delete_run(store, rid):
            deleted.append(rid)
        else:
            missing.append(rid)
    return {
        "deleted_count": len(deleted),
        "deleted_run_ids": deleted,
        "missing_run_ids": missing,
        "scope": "selected",
    }


def _run_filter_clauses(
    *,
    ticker: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    sector: Optional[str],
    industry: Optional[str],
) -> tuple[list[str], list[Any]]:
    where: list[str] = []
    params: list[Any] = []
    if ticker:
        where.append("ticker = ?")
        params.append(normalize_ticker(ticker))
    if date_from:
        where.append("trade_date >= ?")
        params.append(date_from)
    if date_to:
        where.append("trade_date <= ?")
        params.append(date_to)
    if sector:
        where.append("json_extract(dimensions_json, '$.facts.sector') = ?")
        params.append(sector)
    if industry:
        where.append("json_extract(dimensions_json, '$.facts.industry') = ?")
        params.append(industry)
    return where, params


def delete_all_runs(
    store: StateStore,
    *,
    ticker: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
) -> Dict[str, Any]:
    """Delete all runs matching optional filters."""
    sect = (sector or "").strip() or None
    ind = (industry or "").strip() or None
    if (sect or ind) and not d1_history_enabled():
        raise RuntimeError("sector_industry_filters_require_d1")

    if d1_history_enabled():
        return _delete_all_runs_d1(
            ticker=ticker,
            date_from=date_from,
            date_to=date_to,
            sector=sect,
            industry=ind,
        )

    refs = list_runs(
        store,
        ticker=ticker,
        limit=MAX_HISTORY_RUNS_QUERY_LIMIT,
        date_from=date_from,
        date_to=date_to,
    )
    ids = [
        str(r.get("run_id") or r.get("job_id") or "").strip()
        for r in refs
        if isinstance(r, dict)
    ]
    ids = [rid for rid in ids if rid]
    out = delete_runs(store, ids)
    out["scope"] = "filtered"
    return out


def _delete_all_runs_d1(
    *,
    ticker: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    sector: Optional[str],
    industry: Optional[str],
) -> Dict[str, Any]:
    _ensure_d1_schema()
    where, params = _run_filter_clauses(
        ticker=ticker,
        date_from=date_from,
        date_to=date_to,
        sector=sector,
        industry=industry,
    )
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    count_rows = _d1_query(
        f"SELECT COUNT(*) AS c FROM analysis_runs {where_sql}",
        params or None,
    )
    count = int((count_rows[0] if count_rows else {}).get("c") or 0)
    if count:
        _d1_query(f"DELETE FROM analysis_runs {where_sql}", params or None)
    return {
        "deleted_count": count,
        "deleted_run_ids": [],
        "missing_run_ids": [],
        "scope": "filtered" if where else "all",
    }


def default_store() -> StateStore:
    return get_state_store()
