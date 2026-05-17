#!/usr/bin/env python3
"""Cold-start Yahoo sector/industry catalog + constituents into Cloudflare D1.

Run once after D1 env vars are set, then the API reads buckets from D1 (no Yahoo
on every request). Re-run periodically or when Yahoo renames industries.

Examples::

  # Buckets only (~145 rows, fast)
  uv run python scripts/cold_start_yahoo_sectors.py

  # Buckets + US + HK constituent tickers (US slow ~145 calls; HK ~60 seed tickers)
  uv run python scripts/cold_start_yahoo_sectors.py --constituents

  # US only or HK only
  uv run python scripts/cold_start_yahoo_sectors.py --constituents --markets us
  uv run python scripts/cold_start_yahoo_sectors.py --constituents --markets hk

Requires: CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_D1_DATABASE_ID, CLOUDFLARE_API_TOKEN
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))


def main() -> int:
    from api.cloudflare_storage import cloudflare_d1_enabled
    from api.dimensions.sector_industry_catalog import (
        MARKET_HK,
        MARKET_US,
        cold_start_yahoo_sectors_to_d1,
    )

    if not cloudflare_d1_enabled():
        print(
            "D1 is not configured. Set CLOUDFLARE_ACCOUNT_ID, "
            "CLOUDFLARE_D1_DATABASE_ID, and CLOUDFLARE_API_TOKEN.",
            file=sys.stderr,
        )
        return 1

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--constituents",
        action="store_true",
        help="Also fetch and upsert tickers per industry (slow).",
    )
    p.add_argument(
        "--markets",
        default="us,hk",
        help="Comma-separated markets for constituents: us, hk (default: us,hk).",
    )
    args = p.parse_args()

    markets: list[str] = []
    for part in args.markets.split(","):
        token = part.strip().lower()
        if token in ("us", "usa", "u"):
            markets.append(MARKET_US)
        elif token in ("hk", "hkg", "hongkong"):
            markets.append(MARKET_HK)
        elif token:
            print(f"Unknown market {part!r}; use us and/or hk.", file=sys.stderr)
            return 1

    stats = cold_start_yahoo_sectors_to_d1(
        fetch_constituents=args.constituents,
        markets=markets or None,
    )
    print(
        f"Upserted {stats.get('buckets', 0)} sector/industry buckets; "
        f"constituents total={stats.get('constituents', 0)} "
        f"(US={stats.get('constituents_us', 0)}, HK={stats.get('constituents_hk', 0)})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
