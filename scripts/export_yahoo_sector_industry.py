#!/usr/bin/env python3
"""Refresh committed Yahoo sector/industry baseline used by /api/history/coverage."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from api.dimensions.sector_industry_catalog import fetch_yahoo_sector_industry_pairs

_OUT = _REPO_ROOT / "api" / "data" / "yahoo_sector_industry_baseline.json"


def main() -> int:
    pairs = fetch_yahoo_sector_industry_pairs()
    if not pairs:
        print("No pairs fetched from yfinance", file=sys.stderr)
        return 1
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(
        json.dumps({"version": 1, "pairs": pairs}, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(pairs)} pairs to {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
