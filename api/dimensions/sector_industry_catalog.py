"""Yahoo Finance sector/industry catalog aligned with yfinance ``Ticker.info`` facts.

Used to populate ``/api/history/coverage`` with a full grid before any analyses exist.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# yfinance Sector slug keys (stable as of yfinance 0.2.x).
YAHOO_SECTOR_KEYS: tuple[str, ...] = (
    "basic-materials",
    "communication-services",
    "consumer-cyclical",
    "consumer-defensive",
    "energy",
    "financial-services",
    "healthcare",
    "industrials",
    "real-estate",
    "technology",
    "utilities",
)

_CATALOG_CACHE_FILENAME = "yahoo_sector_industry_catalog.json"
_CATALOG_TTL_SECONDS = 7 * 24 * 3600
_BASELINE_PATH = Path(__file__).resolve().parent.parent / "data" / "yahoo_sector_industry_baseline.json"
_HK_TICKER_SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "hk_ticker_seed.txt"

MARKET_US = "US"
MARKET_HK = "HK"


def normalize_sector_industry(sector: Optional[str], industry: Optional[str]) -> Tuple[str, str]:
    """Normalize labels for merge keys (case-insensitive sort, strip whitespace)."""
    s = (sector or "").strip() or "(unknown)"
    i = (industry or "").strip() or "(unknown)"
    return s, i


def _pair_key(sector: str, industry: str) -> Tuple[str, str]:
    s, i = normalize_sector_industry(sector, industry)
    return s.casefold(), i.casefold()


def _catalog_cache_path(data_cache_dir: Optional[Path] = None) -> Path:
    if data_cache_dir is None:
        from tradingagents.default_config import DEFAULT_CONFIG

        base = Path(DEFAULT_CONFIG.get("data_cache_dir") or "./data_cache")
    else:
        base = data_cache_dir
    return base / _CATALOG_CACHE_FILENAME


def _load_baseline_pairs() -> List[Dict[str, str]]:
    if not _BASELINE_PATH.is_file():
        logger.warning("Missing baseline catalog at %s", _BASELINE_PATH)
        return []
    raw = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    pairs = raw.get("pairs") if isinstance(raw, dict) else None
    if not isinstance(pairs, list):
        return []
    out: List[Dict[str, str]] = []
    for item in pairs:
        if not isinstance(item, dict):
            continue
        s = item.get("sector")
        i = item.get("industry")
        if isinstance(s, str) and isinstance(i, str) and s.strip() and i.strip():
            out.append({"sector": s.strip(), "industry": i.strip()})
    return out


def _read_disk_cache(path: Path) -> Optional[List[Dict[str, str]]]:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    fetched_at = raw.get("fetched_at")
    pairs = raw.get("pairs")
    if not isinstance(fetched_at, (int, float)) or not isinstance(pairs, list):
        return None
    if time.time() - float(fetched_at) > _CATALOG_TTL_SECONDS:
        return None
    out: List[Dict[str, str]] = []
    for item in pairs:
        if isinstance(item, dict):
            s, i = item.get("sector"), item.get("industry")
            if isinstance(s, str) and isinstance(i, str) and s.strip() and i.strip():
                out.append({"sector": s.strip(), "industry": i.strip()})
    return out if out else None


def _write_disk_cache(path: Path, pairs: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fetched_at": time.time(), "version": 1, "pairs": pairs}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def fetch_yahoo_catalog_entries() -> List[Dict[str, str]]:
    """Fetch sector/industry rows with Yahoo ``industry_key`` slugs (network)."""
    import yfinance as yf

    entries: List[Dict[str, str]] = []
    for sector_key in YAHOO_SECTOR_KEYS:
        sec = yf.Sector(sector_key)
        sector_name = str(getattr(sec, "name", sector_key) or sector_key)
        industries = sec.industries
        if industries is None or getattr(industries, "empty", True):
            continue
        for industry_key, row in industries.iterrows():
            industry_name = str(row.get("name", industry_key)).strip()
            ikey = str(industry_key).strip()
            if industry_name and ikey:
                entries.append(
                    {
                        "sector": sector_name,
                        "industry": industry_name,
                        "industry_key": ikey,
                    }
                )
    entries.sort(key=lambda p: (p["sector"].lower(), p["industry"].lower()))
    return entries


def fetch_yahoo_sector_industry_pairs() -> List[Dict[str, str]]:
    """Fetch sector/industry pairs from yfinance (network)."""
    return [
        {"sector": e["sector"], "industry": e["industry"]}
        for e in fetch_yahoo_catalog_entries()
    ]


def fetch_yahoo_industry_constituents(industry_key: str) -> List[str]:
    """Ticker symbols for one Yahoo industry (top company lists)."""
    import yfinance as yf

    key = (industry_key or "").strip()
    if not key:
        return []
    ind = yf.Industry(key)
    tickers: set[str] = set()
    for attr in ("top_companies", "top_growth_companies", "top_performing_companies"):
        frame = getattr(ind, attr, None)
        if frame is None or not hasattr(frame, "index"):
            continue
        for sym in frame.index:
            label = str(sym).strip().upper()
            if label and label != "NONE":
                tickers.add(label)
    return sorted(tickers)


def _load_catalog_from_d1() -> List[Dict[str, str]]:
    from api.history import _d1_query, _ensure_d1_schema, d1_history_enabled

    if not d1_history_enabled():
        return []
    _ensure_d1_schema()
    rows = _d1_query(
        """
        SELECT sector, industry FROM yahoo_sector_industry_buckets
        ORDER BY sector, industry
        """
    )
    out: List[Dict[str, str]] = []
    for row in rows:
        sector = row.get("sector")
        industry = row.get("industry")
        if isinstance(sector, str) and isinstance(industry, str) and sector.strip() and industry.strip():
            out.append({"sector": sector.strip(), "industry": industry.strip()})
    return out


def _load_hk_ticker_seed() -> List[str]:
    if not _HK_TICKER_SEED_PATH.is_file():
        return []
    out: List[str] = []
    for line in _HK_TICKER_SEED_PATH.read_text(encoding="utf-8").splitlines():
        s = line.split("#", 1)[0].strip().upper()
        if s:
            out.append(s)
    return sorted(set(out))


def fetch_hk_constituent_rows(entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Map HK-listed tickers into Yahoo sector/industry buckets via yfinance ``info``."""
    import yfinance as yf

    from api.tickers import normalize_ticker

    bucket_by_key: Dict[Tuple[str, str], Dict[str, str]] = {}
    for entry in entries:
        sector = str(entry.get("sector") or "").strip()
        industry = str(entry.get("industry") or "").strip()
        if sector and industry:
            bucket_by_key[_pair_key(sector, industry)] = entry

    rows: List[Dict[str, str]] = []
    for raw in _load_hk_ticker_seed():
        try:
            sym = normalize_ticker(raw)
        except ValueError:
            logger.warning("HK seed skip invalid ticker %r", raw)
            continue
        if not sym.upper().endswith(".HK"):
            continue
        try:
            info = yf.Ticker(sym).info or {}
        except Exception:
            logger.exception("HK yfinance info failed for %s", sym)
            continue
        sector = info.get("sector")
        industry = info.get("industry")
        if not isinstance(sector, str) or not isinstance(industry, str):
            continue
        sector = sector.strip()
        industry = industry.strip()
        if not sector or not industry:
            continue
        bucket = bucket_by_key.get(_pair_key(sector, industry))
        if not bucket:
            continue
        rows.append(
            {
                "sector": sector,
                "industry": industry,
                "industry_key": bucket["industry_key"],
                "market": MARKET_HK,
                "ticker": sym.upper(),
            }
        )
    return rows


def upsert_yahoo_catalog_to_d1(
    entries: List[Dict[str, str]],
    *,
    constituent_rows: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, int]:
    """Upsert Yahoo sector/industry buckets (and optional constituents) into D1."""
    from api.history import _d1_query, _ensure_d1_schema, d1_history_enabled

    if not d1_history_enabled():
        raise RuntimeError("D1 is not configured")
    _ensure_d1_schema()
    now = time.time()
    bucket_count = 0
    constituent_count = 0

    for entry in entries:
        sector = str(entry.get("sector") or "").strip()
        industry = str(entry.get("industry") or "").strip()
        industry_key = str(entry.get("industry_key") or "").strip()
        if not sector or not industry or not industry_key:
            continue
        _d1_query(
            """
            INSERT INTO yahoo_sector_industry_buckets
                (sector, industry, industry_key, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(sector, industry) DO UPDATE SET
                industry_key = excluded.industry_key,
                updated_at = excluded.updated_at
            """,
            [sector, industry, industry_key, now],
        )
        bucket_count += 1

    for row in constituent_rows or []:
        sector = str(row.get("sector") or "").strip()
        industry = str(row.get("industry") or "").strip()
        industry_key = str(row.get("industry_key") or "").strip()
        market = str(row.get("market") or MARKET_US).strip().upper() or MARKET_US
        sym = str(row.get("ticker") or "").strip().upper()
        if not sector or not industry or not industry_key or not sym:
            continue
        _d1_query(
            """
            INSERT INTO yahoo_industry_constituents
                (sector, industry, industry_key, market, ticker, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(sector, industry, ticker) DO UPDATE SET
                industry_key = excluded.industry_key,
                market = excluded.market,
                updated_at = excluded.updated_at
            """,
            [sector, industry, industry_key, market, sym, now],
        )
        constituent_count += 1

    return {"buckets": bucket_count, "constituents": constituent_count}


def cold_start_yahoo_sectors_to_d1(
    *,
    fetch_constituents: bool = True,
    markets: Optional[List[str]] = None,
) -> Dict[str, int]:
    """One-shot batch: pull Yahoo catalog from network and upsert into D1."""
    if markets is None:
        markets = [MARKET_US, MARKET_HK]
    market_set = {m.strip().upper() for m in markets if m and m.strip()}

    entries = fetch_yahoo_catalog_entries()
    if not entries:
        raise RuntimeError("Yahoo sector/industry catalog fetch returned no rows")

    constituent_rows: List[Dict[str, str]] = []
    if fetch_constituents:
        if MARKET_US in market_set:
            for entry in entries:
                sector = entry["sector"]
                industry = entry["industry"]
                us_tickers = fetch_yahoo_industry_constituents(entry["industry_key"])
                for sym in us_tickers:
                    constituent_rows.append(
                        {
                            "sector": sector,
                            "industry": industry,
                            "industry_key": entry["industry_key"],
                            "market": MARKET_US,
                            "ticker": sym,
                        }
                    )
                logger.info(
                    "US constituents sector=%s industry=%s count=%d",
                    sector,
                    industry,
                    len(us_tickers),
                )
        if MARKET_HK in market_set:
            hk_rows = fetch_hk_constituent_rows(entries)
            constituent_rows.extend(hk_rows)
            logger.info("HK constituents mapped %d rows", len(hk_rows))

    stats = upsert_yahoo_catalog_to_d1(entries, constituent_rows=constituent_rows)
    stats["buckets"] = len(entries)
    stats["constituents_us"] = sum(1 for r in constituent_rows if r.get("market") == MARKET_US)
    stats["constituents_hk"] = sum(1 for r in constituent_rows if r.get("market") == MARKET_HK)
    return stats


def list_industry_constituents(
    sector: str,
    industry: str,
    *,
    market: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Constituent tickers for a bucket merged with per-ticker analysis coverage (D1)."""
    from api.history import _d1_query, _ensure_d1_schema, _list_runs_d1, d1_history_enabled

    if not d1_history_enabled():
        raise RuntimeError("constituents_require_d1")

    sect = sector.strip()
    ind = industry.strip()
    if not sect or not ind:
        return []

    _ensure_d1_schema()
    mkt = (market or "").strip().upper()

    all_for_bucket = _d1_query(
        """
        SELECT market, ticker FROM yahoo_industry_constituents
        WHERE sector = ? AND industry = ?
        ORDER BY market, ticker
        """,
        [sect, ind],
    )
    const_rows: list[dict[str, Any]] = list(all_for_bucket)
    if mkt:
        const_rows = [
            r
            for r in all_for_bucket
            if str(r.get("market") or MARKET_US).strip().upper() == mkt
        ]

    # Cold-start may have populated buckets without constituent rows; resolve tickers live.
    if not const_rows and not all_for_bucket:
        key_rows = _d1_query(
            """
            SELECT industry_key FROM yahoo_sector_industry_buckets
            WHERE sector = ? AND industry = ?
            LIMIT 1
            """,
            [sect, ind],
        )
        raw_key = key_rows[0].get("industry_key") if key_rows else None
        ikey = raw_key.strip() if isinstance(raw_key, str) and raw_key.strip() else ""
        if ikey:
            try:
                syms = fetch_yahoo_industry_constituents(ikey)
            except Exception:
                logger.exception(
                    "Live Yahoo constituent fetch failed sector=%s industry=%s key=%s",
                    sect,
                    ind,
                    ikey,
                )
                syms = []
            synth: list[dict[str, Any]] = []
            for sym in syms:
                u = str(sym or "").strip().upper()
                if not u or u == "NONE":
                    continue
                is_hk = u.endswith(".HK")
                mk = MARKET_HK if is_hk else MARKET_US
                if mkt and mk != mkt:
                    continue
                synth.append({"market": mk, "ticker": u})
            const_rows = synth

    runs = _list_runs_d1(
        ticker=None,
        limit=500,
        date_from=None,
        date_to=None,
        sector=sect,
        industry=ind,
    )

    runs_by_ticker: Dict[str, List[Dict[str, Any]]] = {}
    for run in runs:
        t = str(run.get("ticker") or "").strip().upper()
        if not t:
            continue
        runs_by_ticker.setdefault(t, []).append(run)

    def _latest_run(ticker: str) -> Optional[Dict[str, Any]]:
        bucket = runs_by_ticker.get(ticker.upper(), [])
        if not bucket:
            return None
        return max(bucket, key=lambda r: str(r.get("completed_at") or r.get("created_at") or ""))

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for row in const_rows:
        sym = str(row.get("ticker") or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        m = str(row.get("market") or MARKET_US).strip().upper() or MARKET_US
        ticker_runs = runs_by_ticker.get(sym, [])
        latest = _latest_run(sym)
        out.append(
            {
                "ticker": sym,
                "market": m,
                "run_count": len(ticker_runs),
                "has_report": len(ticker_runs) > 0,
                "has_dimensions": bool(latest and latest.get("has_dimensions")),
                "has_commentary": bool(latest and latest.get("has_commentary")),
                "latest_rating": latest.get("rating") if latest else None,
                "latest_date": latest.get("date") if latest else None,
                "latest_run_id": latest.get("run_id") if latest else None,
                "latest_completed_at": latest.get("completed_at") if latest else None,
            }
        )

    for sym, ticker_runs in runs_by_ticker.items():
        if sym in seen:
            continue
        latest = max(ticker_runs, key=lambda r: str(r.get("completed_at") or r.get("created_at") or ""))
        suffix = ".HK" if sym.endswith(".HK") else ""
        out.append(
            {
                "ticker": sym,
                "market": MARKET_HK if suffix else MARKET_US,
                "run_count": len(ticker_runs),
                "has_report": True,
                "has_dimensions": bool(latest.get("has_dimensions")),
                "has_commentary": bool(latest.get("has_commentary")),
                "latest_rating": latest.get("rating"),
                "latest_date": latest.get("date"),
                "latest_run_id": latest.get("run_id"),
                "latest_completed_at": latest.get("completed_at"),
            }
        )

    out.sort(
        key=lambda r: (
            0 if r.get("has_report") else 1,
            str(r.get("ticker") or ""),
        )
    )
    return out


def load_sector_industry_catalog(
    data_cache_dir: Optional[Path] = None,
    *,
    force_refresh: bool = False,
) -> List[Dict[str, str]]:
    """Return Yahoo-aligned pairs: D1 cold-start → disk cache → live fetch → baseline."""
    if not force_refresh:
        d1_rows = _load_catalog_from_d1()
        if d1_rows:
            return d1_rows

    cache_path = _catalog_cache_path(data_cache_dir)
    if not force_refresh:
        cached = _read_disk_cache(cache_path)
        if cached:
            return cached

    try:
        pairs = fetch_yahoo_sector_industry_pairs()
        if pairs:
            try:
                _write_disk_cache(cache_path, pairs)
            except OSError:
                logger.exception("Failed to write sector/industry catalog cache")
            return pairs
    except Exception:
        logger.exception("yfinance sector/industry catalog fetch failed")

    stale = None
    if cache_path.is_file():
        try:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            stale_pairs = raw.get("pairs") if isinstance(raw, dict) else None
            if isinstance(stale_pairs, list) and stale_pairs:
                stale = [
                    {"sector": str(p["sector"]).strip(), "industry": str(p["industry"]).strip()}
                    for p in stale_pairs
                    if isinstance(p, dict) and p.get("sector") and p.get("industry")
                ]
        except (OSError, json.JSONDecodeError):
            pass
    if stale:
        return stale

    baseline = _load_baseline_pairs()
    if baseline:
        return baseline
    return []


def merge_coverage_with_catalog(
    catalog: List[Dict[str, str]],
    aggregates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge D1 aggregate rows onto the full catalog; append orphan aggregate keys."""
    agg_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in aggregates:
        sector = row.get("sector")
        industry = row.get("industry")
        if not isinstance(sector, str) or not isinstance(industry, str):
            continue
        agg_by_key[_pair_key(sector, industry)] = row

    seen: set[Tuple[str, str]] = set()
    merged: List[Dict[str, Any]] = []

    for pair in catalog:
        sector = pair["sector"]
        industry = pair["industry"]
        key = _pair_key(sector, industry)
        if key in seen:
            continue
        seen.add(key)
        agg = agg_by_key.get(key)
        if agg:
            merged.append(
                {
                    "sector": sector,
                    "industry": industry,
                    "run_count": int(agg.get("run_count") or 0),
                    "with_dimensions_count": int(agg.get("with_dimensions_count") or 0),
                    "with_commentary_count": int(agg.get("with_commentary_count") or 0),
                    "latest_completed_at": agg.get("latest_completed_at"),
                }
            )
        else:
            merged.append(
                {
                    "sector": sector,
                    "industry": industry,
                    "run_count": 0,
                    "with_dimensions_count": 0,
                    "with_commentary_count": 0,
                    "latest_completed_at": None,
                }
            )

    extras: List[Dict[str, Any]] = []
    for key, agg in agg_by_key.items():
        if key in seen:
            continue
        extras.append(
            {
                "sector": str(agg.get("sector") or "(unknown)"),
                "industry": str(agg.get("industry") or "(unknown)"),
                "run_count": int(agg.get("run_count") or 0),
                "with_dimensions_count": int(agg.get("with_dimensions_count") or 0),
                "with_commentary_count": int(agg.get("with_commentary_count") or 0),
                "latest_completed_at": agg.get("latest_completed_at"),
            }
        )
    extras.sort(key=lambda r: (str(r["sector"]).lower(), str(r["industry"]).lower()))
    merged.extend(extras)
    return merged


__all__ = [
    "YAHOO_SECTOR_KEYS",
    "MARKET_HK",
    "MARKET_US",
    "cold_start_yahoo_sectors_to_d1",
    "fetch_hk_constituent_rows",
    "fetch_yahoo_catalog_entries",
    "fetch_yahoo_industry_constituents",
    "fetch_yahoo_sector_industry_pairs",
    "list_industry_constituents",
    "load_sector_industry_catalog",
    "merge_coverage_with_catalog",
    "normalize_sector_industry",
    "upsert_yahoo_catalog_to_d1",
]
