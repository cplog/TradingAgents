#!/usr/bin/env python3
"""Pre-warm the dimensions peer cache for a sector+industry.

Usage:
  python scripts/warm_peer_cache.py --sector Technology \
      --industry "Consumer Electronics" --tickers AAPL MSFT GOOGL META AMZN NVDA AMD
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from api.config import build_service_config
from api.dimensions.facts import extract_facts
from api.dimensions.peers import PeerCache, slug_for_sector


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--sector", required=True)
    p.add_argument("--industry", required=True)
    p.add_argument("--tickers", nargs="+", required=True)
    p.add_argument("--cache-dir", default=None,
                   help="Override base cache dir (defaults to service config data_cache_dir)")
    args = p.parse_args(argv)

    slug = slug_for_sector(args.sector, args.industry)
    if not slug:
        print("sector + industry required", file=sys.stderr)
        return 2

    if args.cache_dir:
        base = Path(args.cache_dir)
    else:
        cfg = build_service_config()
        base = Path(cfg.get("data_cache_dir") or "./data_cache")
    cache_dir = base / "peer_facts"
    cache = PeerCache(base_dir=cache_dir)

    today = datetime.utcnow().strftime("%Y-%m-%d")
    facts = {}
    for t in args.tickers:
        try:
            snap, _flags = extract_facts(t, today)
            facts[t] = snap.model_dump()
            print(f"OK   {t}")
        except Exception as exc:
            print(f"SKIP {t}: {exc}", file=sys.stderr)

    cache.write(slug, list(facts.keys()), facts)
    print(f"Wrote {len(facts)} peers to {cache_dir / slug}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
