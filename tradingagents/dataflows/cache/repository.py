"""News persistence + search against local SQLite or Cloudflare D1."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from tradingagents.dataflows.cache.d1_exec import cloudflare_d1_configured, d1_execute_sql
from tradingagents.dataflows.cache.schema import DATA_CACHE_BOOTSTRAP_DDLS


def _backend(cfg: Dict[str, Any]) -> str:
    return str(cfg.get("data_cache_backend") or "none").strip().lower()


def _sqlite_path(cfg: Dict[str, Any]) -> Path:
    base = Path(cfg.get("data_cache_dir") or "./data_cache")
    name = cfg.get("data_cache_sqlite_filename") or "ta_data_cache.db"
    return base / str(name)


def ensure_sqlite_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("\n".join(s + ";" for s in DATA_CACHE_BOOTSTRAP_DDLS))
    conn.commit()


def ensure_schema_for_backend(cfg: Dict[str, Any]) -> None:
    backend = _backend(cfg)
    if backend == "sqlite":
        path = _sqlite_path(cfg)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        try:
            ensure_sqlite_schema(conn)
        finally:
            conn.close()
    elif backend == "d1":
        if not cloudflare_d1_configured():
            raise RuntimeError("data_cache_backend is 'd1' but Cloudflare D1 env is incomplete")
        for ddl in DATA_CACHE_BOOTSTRAP_DDLS:
            d1_execute_sql(ddl)


def _news_row_id(source_id: str, title: str, url: str) -> str:
    raw = f"{source_id}|{title}|{url}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:40]


def upsert_news_items(cfg: Dict[str, Any], rows: List[Dict[str, Any]]) -> int:
    """Insert or replace normalized news rows. Returns rows written."""
    if not rows:
        return 0
    backend = _backend(cfg)
    if backend == "none":
        return 0

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    written = 0

    if backend == "sqlite":
        path = _sqlite_path(cfg)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        try:
            ensure_sqlite_schema(conn)
            for r in rows:
                rid = _news_row_id(
                    str(r.get("source_id") or ""),
                    str(r.get("title") or ""),
                    str(r.get("url") or ""),
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ta_news_items (
                        id, source_id, rank, title, url, content, publish_time,
                        crawl_time, sentiment_score, analysis_note, meta_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rid,
                        str(r.get("source_id") or ""),
                        int(r.get("rank") or 0),
                        str(r.get("title") or ""),
                        str(r.get("url") or "") or None,
                        str(r.get("content") or "") or None,
                        str(r.get("publish_time") or "") or None,
                        str(r.get("crawl_time") or now),
                        r.get("sentiment_score"),
                        str(r.get("analysis_note") or "") or None,
                        json.dumps(r.get("meta_json") or {}, ensure_ascii=False),
                    ),
                )
                written += 1
            conn.commit()
        finally:
            conn.close()
        return written

    if backend == "d1":
        ensure_schema_for_backend(cfg)
        for r in rows:
            rid = _news_row_id(
                str(r.get("source_id") or ""),
                str(r.get("title") or ""),
                str(r.get("url") or ""),
            )
            meta = json.dumps(r.get("meta_json") or {}, ensure_ascii=False)
            d1_execute_sql(
                """
                INSERT OR REPLACE INTO ta_news_items (
                    id, source_id, rank, title, url, content, publish_time,
                    crawl_time, sentiment_score, analysis_note, meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    rid,
                    str(r.get("source_id") or ""),
                    int(r.get("rank") or 0),
                    str(r.get("title") or ""),
                    str(r.get("url") or "") or None,
                    str(r.get("content") or "") or None,
                    str(r.get("publish_time") or "") or None,
                    str(r.get("crawl_time") or now),
                    r.get("sentiment_score"),
                    str(r.get("analysis_note") or "") or None,
                    meta,
                ],
            )
            written += 1
        return written

    raise ValueError(f"Unknown data_cache_backend: {backend}")


def search_cached_news(cfg: Dict[str, Any], query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Substring search on title and content (bounded)."""
    backend = _backend(cfg)
    if backend == "none":
        return []
    q = f"%{(query or '').strip()}%"
    lim = max(1, min(int(limit or 10), 50))

    if backend == "sqlite":
        path = _sqlite_path(cfg)
        if not path.is_file():
            return []
        conn = sqlite3.connect(str(path))
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                """
                SELECT id, source_id, rank, title, url, content, publish_time,
                       crawl_time, sentiment_score, analysis_note, meta_json
                FROM ta_news_items
                WHERE title LIKE ? OR COALESCE(content, '') LIKE ?
                ORDER BY crawl_time DESC
                LIMIT ?
                """,
                (q, q, lim),
            )
            return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    if backend == "d1":
        rows = d1_execute_sql(
            """
            SELECT id, source_id, rank, title, url, content, publish_time,
                   crawl_time, sentiment_score, analysis_note, meta_json
            FROM ta_news_items
            WHERE title LIKE ? OR COALESCE(content, '') LIKE ?
            ORDER BY crawl_time DESC
            LIMIT ?
            """,
            [q, q, lim],
        )
        return [dict(r) for r in rows]

    raise ValueError(f"Unknown data_cache_backend: {backend}")


def _stock_vendor_tag(cfg: Dict[str, Any]) -> str:
    explicit = str(cfg.get("data_cache_stock_vendor_tag") or "").strip()
    if explicit:
        return explicit[:48]
    try:
        from tradingagents.dataflows.catalog import get_category_for_method
        from tradingagents.dataflows.interface import get_vendor

        cat = get_category_for_method("get_stock_data")
        raw = str(get_vendor(cat, "get_stock_data"))
        first = raw.split(",")[0].strip()
        return (first or "unknown")[:48]
    except Exception:
        return "unknown"


def _sql_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except (TypeError, ValueError):
        return None


def upsert_stock_bars(
    cfg: Dict[str, Any],
    ticker: str,
    vendor: str,
    rows: List[Dict[str, Any]],
) -> int:
    """Upsert daily OHLCV rows into ``ta_stock_bars``."""
    if not rows:
        return 0
    backend = _backend(cfg)
    if backend == "none":
        return 0

    sym = ticker.strip().upper()
    ven = (vendor or "unknown").strip()[:48]
    written = 0

    if backend == "sqlite":
        path = _sqlite_path(cfg)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        try:
            ensure_sqlite_schema(conn)
            for r in rows:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ta_stock_bars (
                        ticker, bar_date, open, high, low, close, volume,
                        change_pct, vendor
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sym,
                        str(r.get("bar_date") or ""),
                        _sql_float(r.get("open")),
                        _sql_float(r.get("high")),
                        _sql_float(r.get("low")),
                        _sql_float(r.get("close")),
                        _sql_float(r.get("volume")),
                        _sql_float(r.get("change_pct")),
                        ven,
                    ),
                )
                written += 1
            conn.commit()
        finally:
            conn.close()
        return written

    if backend == "d1":
        ensure_schema_for_backend(cfg)
        for r in rows:
            d1_execute_sql(
                """
                INSERT OR REPLACE INTO ta_stock_bars (
                    ticker, bar_date, open, high, low, close, volume,
                    change_pct, vendor
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    sym,
                    str(r.get("bar_date") or ""),
                    _sql_float(r.get("open")),
                    _sql_float(r.get("high")),
                    _sql_float(r.get("low")),
                    _sql_float(r.get("close")),
                    _sql_float(r.get("volume")),
                    _sql_float(r.get("change_pct")),
                    ven,
                ],
            )
            written += 1
        return written

    raise ValueError(f"Unknown data_cache_backend: {backend}")


def fetch_cached_stock_bars(
    cfg: Dict[str, Any],
    ticker: str,
    start_date: str,
    end_date: str,
    *,
    vendor: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """Load cached OHLCV rows for a ticker and inclusive date range."""
    backend = _backend(cfg)
    if backend == "none":
        return []
    sym = ticker.strip().upper()
    lim = max(1, min(int(limit or 500), 5000))
    params: List[Any]
    if vendor:
        sql = """
            SELECT ticker, bar_date, open, high, low, close, volume, change_pct, vendor
            FROM ta_stock_bars
            WHERE ticker = ? AND bar_date >= ? AND bar_date <= ? AND vendor = ?
            ORDER BY bar_date ASC
            LIMIT ?
        """
        params = [sym, start_date.strip(), end_date.strip(), vendor.strip()[:48], lim]
    else:
        sql = """
            SELECT ticker, bar_date, open, high, low, close, volume, change_pct, vendor
            FROM ta_stock_bars
            WHERE ticker = ? AND bar_date >= ? AND bar_date <= ?
            ORDER BY bar_date ASC
            LIMIT ?
        """
        params = [sym, start_date.strip(), end_date.strip(), lim]

    if backend == "sqlite":
        path = _sqlite_path(cfg)
        if not path.is_file():
            return []
        conn = sqlite3.connect(str(path))
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql, tuple(params))
            return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    if backend == "d1":
        rows = d1_execute_sql(sql, params)
        return [dict(r) for r in rows]

    raise ValueError(f"Unknown data_cache_backend: {backend}")


def maybe_autocache_stock_bars_from_payload(
    cfg: Dict[str, Any],
    ticker: str,
    start_date: str,
    end_date: str,
    payload: str,
) -> int:
    """If enabled, parse a ``get_stock_data`` CSV-style payload and persist bars."""
    if not bool(cfg.get("data_cache_auto_stock_bars")):
        return 0
    if _backend(cfg) == "none":
        return 0
    from tradingagents.dataflows.cache.stock_csv import parse_stock_data_csv_payload

    rows = parse_stock_data_csv_payload(payload)
    if not rows:
        return 0
    tag = _stock_vendor_tag(cfg)
    return upsert_stock_bars(cfg, ticker, tag, rows)


def cache_status_message(cfg: Dict[str, Any]) -> str:
    b = _backend(cfg)
    if b == "none":
        return "Data cache is disabled (data_cache_backend=none)."
    if b == "sqlite":
        return f"Data cache: SQLite at {_sqlite_path(cfg)}"
    if b == "d1":
        ok = cloudflare_d1_configured()
        return (
            "Data cache: Cloudflare D1 (same credentials as API history)"
            if ok
            else "Data cache: D1 selected but CLOUDFLARE_* env incomplete"
        )
    return f"Data cache: unknown backend {b!r}"
