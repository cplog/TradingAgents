#!/usr/bin/env python3
"""Pre-warm dimensions peer universes into local JSON and optionally Cloudflare D1.

Slug strategies (stored under ``<data_cache_dir>/peer_facts/<slug>.json``):

  * ``global`` — legacy fallback ``Sector__Industry`` (cross-exchange).
  * ``local`` — ``ExchangeCurrency__Sector__Industry`` peers on the same market.
  * ``sector`` — ``ExchangeCurrency__Sector__SECTOR_WIDE`` broad local sector peers.

When ``CLOUDFLARE_ACCOUNT_ID``, ``CLOUDFLARE_D1_DATABASE_ID``, and ``CLOUDFLARE_API_TOKEN``
are set, member rows are also upserted into D1 tables ``dimension_peer_*``.

Examples::

  python scripts/warm_peer_cache.py global \\
      --sector Technology --industry "Consumer Electronics" \\
      --tickers AAPL MSFT GOOGL META AMZN NVDA AMD

  python scripts/warm_peer_cache.py local --exchange HKG --currency HKD \\
      --sector "Financial Services" --industry "Insurance - Life" \\
      --tickers 1299.HK 2318.HK 2628.HK
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from api.config import build_service_config
from api.dimensions.facts import extract_facts
from api.dimensions.peer_store import persist_dimension_peer_universe
from api.dimensions.peers import (
    LOCAL_SECTOR_WIDE_INDUSTRY,
    PeerCache,
    market_bucket_from_exchange_currency,
    slug_for_local_industry_universe,
    slug_for_local_sector_universe,
    slug_for_sector,
)
from api.history import d1_history_enabled


def _norm_upper(s: Optional[str]) -> str:
    return (s or "").strip().upper()


def _validate_snapshot(
    _mode: str,
    *,
    sector: str,
    industry: Optional[str],
    exchange_expect: Optional[str],
    currency_expect: Optional[str],
    snap_sector: Optional[str],
    snap_industry: Optional[str],
    snap_exchange: Optional[str],
    snap_currency: Optional[str],
) -> list[str]:
    errs: list[str] = []
    if _norm_upper(snap_sector) != _norm_upper(sector):
        errs.append(f"sector mismatch (expected {sector!r}, got {snap_sector!r})")
    if industry is not None and _norm_upper(snap_industry) != _norm_upper(industry):
        errs.append(f"industry mismatch (expected {industry!r}, got {snap_industry!r})")
    if exchange_expect and _norm_upper(snap_exchange) != _norm_upper(exchange_expect):
        errs.append(f"exchange mismatch (expected {exchange_expect!r}, got {snap_exchange!r})")
    if currency_expect and _norm_upper(snap_currency) != _norm_upper(currency_expect):
        errs.append(f"currency mismatch (expected {currency_expect!r}, got {snap_currency!r})")
    return errs


def _derive_market_bucket(
    *,
    exchange: Optional[str],
    currency: Optional[str],
    first_ticker_facts: tuple[Optional[str], Optional[str]],
) -> tuple[str, Optional[str], Optional[str]]:
    ex = exchange or first_ticker_facts[0]
    cur = currency or first_ticker_facts[1]
    mb = market_bucket_from_exchange_currency(ex, cur)
    return (mb or ""), ex, cur


def _run_bulk(
    tickers: List[str],
    today: str,
    cache: PeerCache,
    cache_dir: Path,
    no_d1: bool,
) -> int:
    """Extract facts for all tickers, group by metadata, and warm every slug with >=3 peers."""
    from collections import defaultdict

    raw_facts: Dict[str, Dict[str, Any]] = {}
    skipped = 0
    for t in tickers:
        try:
            snap, _ = extract_facts(t, today)
            raw_facts[t] = snap.model_dump()
            print(f"OK   {t}")
        except Exception as exc:
            print(f"SKIP {t}: {exc}", file=sys.stderr)
            skipped += 1

    if not raw_facts:
        print("No valid facts extracted.", file=sys.stderr)
        return 3

    # Group by (sector, industry, exchange, currency)
    GroupKey = Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]
    by_group: Dict[GroupKey, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for t, f in raw_facts.items():
        key = (f.get("sector"), f.get("industry"), f.get("exchange"), f.get("currency"))
        by_group[key][t] = f

    written = 0
    for (sector, industry, exchange, currency), facts in by_group.items():
        if len(facts) < 3:
            continue
        if not sector or not industry:
            continue
        mb = market_bucket_from_exchange_currency(exchange, currency)

        # Global industry
        g_slug = slug_for_sector(sector, industry)
        if g_slug:
            cache.write(g_slug, list(facts.keys()), facts)
            print(f"Wrote global  {g_slug} ({len(facts)} peers)")
            if not no_d1 and d1_history_enabled():
                try:
                    persist_dimension_peer_universe(
                        g_slug, scope="global", sector=sector, industry=industry,
                        facts=facts, exchange=None, currency=None,
                    )
                except Exception as exc:
                    print(f"D1 upsert failed for {g_slug}: {exc}", file=sys.stderr)
            written += 1

        # Local industry + local sector-wide
        if mb:
            li_slug = slug_for_local_industry_universe(mb, sector, industry)
            if li_slug:
                cache.write(li_slug, list(facts.keys()), facts)
                print(f"Wrote local   {li_slug} ({len(facts)} peers)")
                if not no_d1 and d1_history_enabled():
                    try:
                        persist_dimension_peer_universe(
                            li_slug, scope="local", sector=sector, industry=industry,
                            facts=facts, exchange=exchange, currency=currency,
                        )
                    except Exception as exc:
                        print(f"D1 upsert failed for {li_slug}: {exc}", file=sys.stderr)
                written += 1

            ls_slug = slug_for_local_sector_universe(mb, sector)
            if ls_slug:
                cache.write(ls_slug, list(facts.keys()), facts)
                print(f"Wrote sector  {ls_slug} ({len(facts)} peers)")
                if not no_d1 and d1_history_enabled():
                    try:
                        persist_dimension_peer_universe(
                            ls_slug, scope="sector", sector=sector,
                            industry=LOCAL_SECTOR_WIDE_INDUSTRY,
                            facts=facts, exchange=exchange, currency=currency,
                        )
                    except Exception as exc:
                        print(f"D1 upsert failed for {ls_slug}: {exc}", file=sys.stderr)
                written += 1

    print(f"\nBulk warm complete: {written} slugs written from {len(raw_facts)} tickers ({skipped} skipped).")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "mode",
        choices=("global", "local", "sector", "bulk"),
        help="Peer universe shape: global sector/industry, local industry, local sector-wide, or bulk (auto-detect all slugs from tickers).",
    )
    p.add_argument("--sector", default=None, help="Yahoo-style sector string")
    p.add_argument(
        "--industry",
        help="Yahoo-style industry string (required for global and local modes)",
    )
    p.add_argument("--exchange", default=None, help="yfinance exchange (e.g. HKG, NMS)")
    p.add_argument("--currency", default=None, help="ISO currency (e.g. HKD, USD)")
    p.add_argument("--tickers", nargs="+", required=True)
    p.add_argument(
        "--cache-dir",
        default=None,
        help="Override base cache dir (defaults to service config data_cache_dir)",
    )
    p.add_argument(
        "--no-d1",
        action="store_true",
        help="Skip Cloudflare D1 upsert even when credentials are present.",
    )
    p.add_argument(
        "--date",
        default=None,
        help="As-of date YYYY-MM-DD for fact extraction (default: UTC today)",
    )
    args = p.parse_args(argv)

    if args.mode in ("global", "local") and not args.industry:
        print("--industry is required for global and local modes", file=sys.stderr)
        return 2
    if args.mode in ("global", "local", "sector") and not args.sector:
        print("--sector is required for global, local, and sector modes", file=sys.stderr)
        return 2

    if args.cache_dir:
        base = Path(args.cache_dir)
    else:
        cfg = build_service_config()
        base = Path(cfg.get("data_cache_dir") or "./data_cache")
    cache_dir = base / "peer_facts"
    cache = PeerCache(base_dir=cache_dir)

    today = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Bulk mode: extract all tickers, group by sector/industry/exchange/currency,
    # then warm every slug that has >=3 members.
    if args.mode == "bulk":
        return _run_bulk(
            tickers=args.tickers,
            today=today,
            cache=cache,
            cache_dir=cache_dir,
            no_d1=args.no_d1,
        )

    # Derive market bucket from first ticker if exchange/currency omitted (local/sector).
    first_ex: Optional[str] = None
    first_cur: Optional[str] = None
    if args.mode in ("local", "sector"):
        try:
            first_snap, _ = extract_facts(args.tickers[0], today)
            first_ex, first_cur = first_snap.exchange, first_snap.currency
        except Exception as exc:
            print(f"Could not infer market from {args.tickers[0]}: {exc}", file=sys.stderr)
            return 2

    mb, resolved_ex, resolved_cur = _derive_market_bucket(
        exchange=args.exchange,
        currency=args.currency,
        first_ticker_facts=(first_ex, first_cur),
    )

    slug: Optional[str] = None
    scope: str = args.mode
    industry_for_row: str

    if args.mode == "global":
        assert args.industry is not None
        slug = slug_for_sector(args.sector, args.industry)
        industry_for_row = args.industry
        resolved_ex, resolved_cur = None, None
    elif args.mode == "local":
        assert args.industry is not None
        if not mb:
            print("Could not build market bucket; pass --exchange and --currency", file=sys.stderr)
            return 2
        slug = slug_for_local_industry_universe(mb, args.sector, args.industry)
        industry_for_row = args.industry
    else:  # sector-wide on one market
        if not mb:
            print("Could not build market bucket; pass --exchange and --currency", file=sys.stderr)
            return 2
        slug = slug_for_local_sector_universe(mb, args.sector)
        industry_for_row = LOCAL_SECTOR_WIDE_INDUSTRY

    if not slug:
        print("Could not compute peer slug", file=sys.stderr)
        return 2

    facts: dict = {}
    skipped = 0
    for t in args.tickers:
        try:
            snap, _flags = extract_facts(t, today)
            ind_expect: Optional[str] = None
            if args.mode == "global":
                ind_expect = args.industry
            elif args.mode == "local":
                ind_expect = args.industry
            else:
                ind_expect = None

            v_errs = _validate_snapshot(
                args.mode,
                sector=args.sector,
                industry=ind_expect,
                exchange_expect=resolved_ex,
                currency_expect=resolved_cur,
                snap_sector=snap.sector,
                snap_industry=snap.industry,
                snap_exchange=snap.exchange,
                snap_currency=snap.currency,
            )
            if v_errs:
                print(f"SKIP {t}: " + "; ".join(v_errs), file=sys.stderr)
                skipped += 1
                continue
            facts[t] = snap.model_dump()
            print(f"OK   {t}")
        except Exception as exc:
            print(f"SKIP {t}: {exc}", file=sys.stderr)
            skipped += 1

    if len(facts) < 3:
        print(
            f"Need at least 3 valid tickers for percentile math; got {len(facts)} "
            f"(skipped {skipped}).",
            file=sys.stderr,
        )
        return 3

    cache.write(slug, list(facts.keys()), facts)
    print(f"Wrote {len(facts)} peers to {cache_dir / (slug + '.json')}")

    if not args.no_d1 and d1_history_enabled():
        try:
            persist_dimension_peer_universe(
                slug,
                scope=scope,
                sector=args.sector,
                industry=industry_for_row,
                facts=facts,
                exchange=resolved_ex,
                currency=resolved_cur,
            )
            print("Upserted peer universe to Cloudflare D1.")
        except Exception as exc:
            print(f"D1 upsert failed (local JSON still written): {exc}", file=sys.stderr)
    elif d1_history_enabled() and args.no_d1:
        print("Skipping D1 upsert (--no-d1).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
