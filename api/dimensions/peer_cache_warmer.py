"""Peer cache warming: pre-build dimension peer universes for common sectors.

Run as a one-shot CLI command or scheduled job.  Warms both D1 (when configured)
and on-disk ``peer_facts/`` JSON caches so that subsequent analysis runs hit
pre-computed peer percentiles instead of cold-starting every time.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from api.dimensions.facts import extract_facts
from api.dimensions.peers import (
    LOCAL_SECTOR_WIDE_INDUSTRY,
    PeerCache,
    market_bucket_from_exchange_currency,
    slug_for_local_industry_universe,
    slug_for_local_sector_universe,
    slug_for_sector,
)
from api.dimensions.peer_store import persist_dimension_peer_universe
from api.dimensions.schemas import FactSnapshot
from api.dimensions.sector_industry_catalog import (
    MARKET_HK,
    MARKET_US,
    fetch_yahoo_industry_constituents,
    load_sector_industry_catalog,
)

logger = logging.getLogger(__name__)

# Default: warm the top N tickers per industry.  yfinance ``Industry`` pages
# return ~30–50 tickers; we cap at 20 to keep wall-clock reasonable.
_DEFAULT_MAX_TICKERS_PER_INDUSTRY = 20

# Sectors that cover the vast majority of analysis traffic.
# If None, all sectors from the catalog are warmed.
_DEFAULT_PRIORITY_SECTORS: Optional[Tuple[str, ...]] = None


def _warm_slug(
    slug: str,
    scope: str,
    sector: str,
    industry: str,
    tickers: List[str],
    as_of_date: str,
    peer_facts_dir: Path,
    max_tickers: int,
) -> Dict[str, Any]:
    """Extract facts for ``tickers`` and write to both D1 and disk cache."""
    tickers = tickers[:max_tickers]
    facts_by_ticker: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []

    for sym in tickers:
        try:
            snap, _flags = extract_facts(sym, as_of_date)
            facts_by_ticker[sym] = snap.model_dump()
        except Exception as exc:
            errors.append(f"{sym}: {exc}")
            logger.debug("Peer fact extraction failed for %s: %s", sym, exc)

    # Write to disk cache (always, so local-only deployments work)
    cache = PeerCache(base_dir=peer_facts_dir)
    cache.write(slug, list(facts_by_ticker.keys()), facts_by_ticker)

    # Write to D1 when configured
    d1_ok = False
    try:
        d1_ok = persist_dimension_peer_universe(
            slug,
            scope=scope,
            sector=sector,
            industry=industry,
            facts=facts_by_ticker,
        )
    except Exception as exc:
        logger.warning("D1 peer persist failed for %s: %s", slug, exc)

    return {
        "slug": slug,
        "scope": scope,
        "sector": sector,
        "industry": industry,
        "tickers_attempted": len(tickers),
        "facts_extracted": len(facts_by_ticker),
        "errors": errors,
        "d1_persisted": d1_ok,
    }


def warm_peer_cache(
    *,
    as_of_date: Optional[str] = None,
    data_cache_dir: Optional[Path] = None,
    max_tickers_per_industry: int = _DEFAULT_MAX_TICKERS_PER_INDUSTRY,
    priority_sectors: Optional[Tuple[str, ...]] = _DEFAULT_PRIORITY_SECTORS,
    max_workers: int = 4,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Warm peer fact caches for all (or priority) sector/industry pairs.

    Args:
        as_of_date: Facts snapshot date (default: today UTC).
        data_cache_dir: Root for ``peer_facts/`` disk cache.
        max_tickers_per_industry: Cap tickers fetched per industry.
        priority_sectors: If set, only warm these sector names (case-insensitive).
        max_workers: Parallel industry fetches (yfinance is I/O bound).
        dry_run: Log what would be warmed without extracting facts.

    Returns:
        Summary dict with ``warmed``, ``failed``, ``total_tickers``, ``elapsed_sec``.
    """
    if as_of_date is None:
        as_of_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if data_cache_dir is None:
        from tradingagents.default_config import DEFAULT_CONFIG

        data_cache_dir = Path(DEFAULT_CONFIG.get("data_cache_dir") or "./data_cache")

    peer_facts_dir = data_cache_dir / "peer_facts"
    peer_facts_dir.mkdir(parents=True, exist_ok=True)

    catalog = load_sector_industry_catalog()
    if not catalog:
        raise RuntimeError("Sector/industry catalog is empty; cannot warm peer cache.")

    # Build work list: each item is (slug, scope, sector, industry, tickers)
    work_items: List[Tuple[str, str, str, str, List[str]]] = []

    for entry in catalog:
        sector = str(entry.get("sector") or "").strip()
        industry = str(entry.get("industry") or "").strip()
        industry_key = str(entry.get("industry_key") or "").strip()
        if not sector or not industry or not industry_key:
            continue

        if priority_sectors and sector.lower() not in [
            s.lower() for s in priority_sectors
        ]:
            continue

        # We warm three scopes per pair:
        # 1. Global sector+industry (no market bucket)
        # 2. US market sector+industry
        # 3. US market sector-wide
        # HK is handled separately via the seed file; skip here to avoid
        # overwhelming yfinance with .HK tickers.

        # Global scope
        slug_g = slug_for_sector(sector, industry)
        if slug_g:
            tickers = fetch_yahoo_industry_constituents(industry_key)
            if tickers:
                work_items.append((slug_g, "global", sector, industry, tickers))

        # US local scopes (NMS.USD is the most common US bucket)
        mb = "NMS.USD"
        slug_li = slug_for_local_industry_universe(mb, sector, industry)
        if slug_li:
            # Same tickers as global for US-listed names; we re-use them.
            # In practice many are US-listed, so this is a good approximation.
            us_tickers = [t for t in tickers if not t.endswith(".HK")]
            if us_tickers:
                work_items.append((slug_li, "local", sector, industry, us_tickers))

        slug_ls = slug_for_local_sector_universe(mb, sector)
        if slug_ls:
            # Sector-wide: we use the same tickers for now; the cache will
            # accumulate across industries as more are warmed.
            if us_tickers:
                work_items.append((slug_ls, "local_sector", sector, LOCAL_SECTOR_WIDE_INDUSTRY, us_tickers))

    if dry_run:
        logger.info(
            "DRY RUN: would warm %d slugs with ~%d total tickers",
            len(work_items),
            sum(len(t[4]) for t in work_items),
        )
        return {
            "dry_run": True,
            "slugs": len(work_items),
            "total_tickers": sum(len(t[4]) for t in work_items),
        }

    warmed: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    total_extracted = 0

    import time
    t0 = time.time()

    # Sequential execution: yfinance is already parallel internally and
    # rate-limits aggressively.  ThreadPoolExecutor helps when the bottleneck
    # is the HTTP round-trip, but for fact extraction (multiple yfinance calls
    # per ticker) we keep workers low to avoid bans.
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _warm_slug,
                slug,
                scope,
                sector,
                industry,
                tickers,
                as_of_date,
                peer_facts_dir,
                max_tickers_per_industry,
            ): (slug, sector, industry)
            for slug, scope, sector, industry, tickers in work_items
        }

        for future in as_completed(futures):
            slug, sector, industry = futures[future]
            try:
                result = future.result()
                warmed.append(result)
                total_extracted += result["facts_extracted"]
                logger.info(
                    "Warmed %s (%s / %s): %d/%d facts extracted",
                    slug,
                    sector,
                    industry,
                    result["facts_extracted"],
                    result["tickers_attempted"],
                )
            except Exception as exc:
                logger.exception("Warm failed for %s (%s / %s)", slug, sector, industry)
                failed.append({"slug": slug, "sector": sector, "industry": industry, "error": str(exc)})

    elapsed = time.time() - t0

    summary = {
        "as_of_date": as_of_date,
        "slugs_warmed": len(warmed),
        "slugs_failed": len(failed),
        "total_tickers_attempted": sum(r["tickers_attempted"] for r in warmed),
        "total_facts_extracted": total_extracted,
        "elapsed_sec": round(elapsed, 1),
        "warmed": warmed,
        "failed": failed,
    }

    logger.info(
        "Peer cache warm complete: %d slugs warmed, %d failed, %d facts in %.1fs",
        summary["slugs_warmed"],
        summary["slugs_failed"],
        summary["total_facts_extracted"],
        summary["elapsed_sec"],
    )

    return summary


__all__ = ["warm_peer_cache"]
