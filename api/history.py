"""Durable analysis history.

Storage strategy (auto-selected):
1) Cloudflare D1 (scalable querying) when configured.
2) StateStore fallback (Cloudflare KV or local JSON file).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from api.state_store import StateStore, get_state_store
from api.tickers import _safe_ticker_component, normalize_ticker, validate_date

logger = logging.getLogger(__name__)

KEY_PREFIX_RUN = "history:run:"
KEY_PREFIX_TICKER_INDEX = "history:index:ticker:"
KEY_GLOBAL_INDEX = "history:index:global"

MAX_TICKER_INDEX = 200
MAX_GLOBAL_INDEX = 500

_d1_initialized = False


def _d1_config() -> Optional[dict[str, str]]:
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    db_id = os.getenv("CLOUDFLARE_D1_DATABASE_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    if account and db_id and token:
        return {"account": account, "db_id": db_id, "token": token}
    return None


def d1_history_enabled() -> bool:
    """True when history should use Cloudflare D1 as primary backend."""
    return _d1_config() is not None


def _d1_query(sql: str, params: Optional[list[Any]] = None) -> list[dict[str, Any]]:
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
    resp = requests.post(url, headers=headers, json=body, timeout=35)
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
    _d1_initialized = True


def _run_key(job_id: str) -> str:
    return f"{KEY_PREFIX_RUN}{job_id}"


def _ticker_index_key(ticker: str) -> str:
    safe = _safe_ticker_component(ticker.strip().upper())
    return f"{KEY_PREFIX_TICKER_INDEX}{safe}"


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
    dims = rec.get("dimensions") or {}
    fs = dims.get("factor_scores") if isinstance(dims, dict) else None
    if isinstance(fs, dict):
        scores: Dict[str, Any] = {}
        for name in ("value", "growth", "quality", "momentum", "low_risk", "sentiment"):
            v = fs.get(name)
            if isinstance(v, dict) and v.get("score") is not None:
                scores[name] = v["score"]
        if scores:
            ref["factor_scores"] = scores
    return ref


def _merge_config_snapshot(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Non-sensitive fields for history / compare."""
    if not config:
        return {}
    out: Dict[str, Any] = {}
    for k in (
        "llm_provider",
        "deep_think_llm",
        "quick_think_llm",
        "max_debate_rounds",
        "max_risk_discuss_rounds",
        "output_language",
    ):
        if k in config and config[k] is not None:
            out[k] = config[k]
    return out


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
        "structured": result.get("structured"),
        "artifacts_path": result.get("artifacts_path"),
        "completed_at": result.get("completed_at"),
        "created_at": created_iso,
        "batch_id": batch_id,
        "config_snapshot": _merge_config_snapshot(config_snapshot),
        "dimensions": result.get("dimensions"),
        "dimensions_commentary": result.get("dimensions_commentary"),
        "dimensions_error": result.get("dimensions_error"),
    }

    if d1_history_enabled():
        try:
            _persist_d1(full)
            return
        except Exception:
            logger.exception("D1 persist failed; falling back to state store")

    store.put_json(_run_key(job_id), full)

    ref = _ref_from_record(full)
    _prepend_ref(store, _ticker_index_key(norm_ticker), ref, MAX_TICKER_INDEX)
    _prepend_ref(store, KEY_GLOBAL_INDEX, ref, MAX_GLOBAL_INDEX)


def _persist_d1(full: Dict[str, Any]) -> None:
    _ensure_d1_schema()
    _d1_query(
        """
        INSERT INTO analysis_runs (
            run_id, job_id, ticker, trade_date, rating, confidence,
            reports_json, structured_json, artifacts_path,
            completed_at, created_at, batch_id, config_snapshot_json,
            dimensions_json, dimensions_commentary_json, dimensions_error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            dimensions_error = excluded.dimensions_error
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
        try:
            row = _get_run_d1(run_id)
            if row:
                return row
        except Exception:
            logger.exception("D1 get_run failed; falling back to state store")
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


def list_runs(
    store: StateStore,
    *,
    ticker: Optional[str] = None,
    limit: int = 50,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return compact refs, newest-first."""
    lim = max(1, min(limit, 200))

    if d1_history_enabled():
        try:
            return _list_runs_d1(
                ticker=ticker,
                limit=lim,
                date_from=date_from,
                date_to=date_to,
            )
        except Exception:
            logger.exception("D1 list_runs failed; falling back to state store")

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
        out.append(r)
        if len(out) >= lim:
            break
    return out


def _list_runs_d1(
    *,
    ticker: Optional[str],
    limit: int,
    date_from: Optional[str],
    date_to: Optional[str],
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
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"""
        SELECT run_id, job_id, ticker, trade_date, rating, confidence,
               completed_at, created_at, batch_id, dimensions_json
        FROM analysis_runs
        {where_sql}
        ORDER BY completed_at DESC, created_at DESC
        LIMIT ?
    """
    params.append(limit)
    rows = _d1_query(sql, params)
    out: list[dict[str, Any]] = []
    for row in rows:
        dims_raw = row.get("dimensions_json")
        dimensions = (
            json.loads(dims_raw) if isinstance(dims_raw, str) and dims_raw else None
        )
        base = {
            "run_id": row.get("run_id"),
            "job_id": row.get("job_id"),
            "ticker": row.get("ticker"),
            "date": row.get("trade_date"),
            "rating": row.get("rating"),
            "confidence": row.get("confidence"),
            "completed_at": row.get("completed_at"),
            "created_at": row.get("created_at"),
            "batch_id": row.get("batch_id"),
            "dimensions": dimensions if isinstance(dimensions, dict) else None,
        }
        out.append(_ref_from_record(base))
    return out


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


def delete_run(store: StateStore, run_id: str) -> bool:
    """Delete a run from history storage and indexes."""
    rid = (run_id or "").strip()
    if not rid:
        return False

    if d1_history_enabled():
        try:
            return _delete_run_d1(rid)
        except Exception:
            logger.exception("D1 delete_run failed; falling back to state store")

    rec = get_run(store, rid)
    if not rec:
        return False

    store.put_json(_run_key(rid), None)
    _remove_ref(store, KEY_GLOBAL_INDEX, rid)

    ticker = rec.get("ticker")
    if isinstance(ticker, str) and ticker.strip():
        try:
            norm_ticker = normalize_ticker(ticker)
        except ValueError:
            norm_ticker = None
        if norm_ticker:
            _remove_ref(store, _ticker_index_key(norm_ticker), rid)
    return True


def _remove_ref(store: StateStore, index_key: str, run_id: str) -> None:
    cur = store.get_json(index_key)
    rows: List[Dict[str, Any]] = cur if isinstance(cur, list) else []
    filtered = [r for r in rows if (r.get("run_id") or r.get("job_id")) != run_id]
    store.put_json(index_key, filtered)


def _delete_run_d1(run_id: str) -> bool:
    _ensure_d1_schema()
    rows = _d1_query("SELECT run_id FROM analysis_runs WHERE run_id = ? LIMIT 1", [run_id])
    if not rows:
        return False
    _d1_query("DELETE FROM analysis_runs WHERE run_id = ?", [run_id])
    return True


def default_store() -> StateStore:
    return get_state_store()
