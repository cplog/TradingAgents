"""Sector peer cache + percentile rank math for dimensions factor scoring."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

logger = logging.getLogger(__name__)

# Synthetic industry token for "all tickers in this sector on this exchange/currency".
LOCAL_SECTOR_WIDE_INDUSTRY = "SECTOR_WIDE"


def sanitize_slug_part(value: str) -> str:
    """Filesystem-safe segment for peer cache slugs (matches PeerCache._path rules)."""
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in value.strip())


def market_bucket_from_exchange_currency(
    exchange: Optional[str], currency: Optional[str],
) -> Optional[str]:
    """Market bucket like ``HKG.HKD`` from yfinance ``exchange`` + ``currency``."""
    if not exchange or not currency:
        return None
    ex = exchange.strip().upper()
    cur = currency.strip().upper()
    if not ex or not cur:
        return None
    return f"{ex}.{cur}"


def slug_for_local_industry_universe(
    market_bucket: Optional[str], sector: Optional[str], industry: Optional[str],
) -> Optional[str]:
    if not market_bucket or not sector or not industry:
        return None
    return "__".join((
        sanitize_slug_part(market_bucket),
        sanitize_slug_part(sector),
        sanitize_slug_part(industry),
    ))


def slug_for_local_sector_universe(
    market_bucket: Optional[str], sector: Optional[str],
) -> Optional[str]:
    if not market_bucket or not sector:
        return None
    return "__".join((
        sanitize_slug_part(market_bucket),
        sanitize_slug_part(sector),
        sanitize_slug_part(LOCAL_SECTOR_WIDE_INDUSTRY),
    ))


def peer_universe_label_local(
    market_bucket: str, sector: str, industry: str,
) -> str:
    return f"market:{market_bucket}|sector:{sector}|industry:{industry}"


def peer_universe_label_local_sector_group(market_bucket: str, sector: str) -> str:
    return (
        f"market:{market_bucket}|sector:{sector}|"
        f"peer_group:{LOCAL_SECTOR_WIDE_INDUSTRY}"
    )


def percentile_rank(value: Optional[float], peers: Iterable[Optional[float]]) -> Optional[float]:
    """Return percentile rank (0..1) of `value` within `peers`. None if <3 usable peers.

    Uses the mid-rank ("fractional") convention:
        (count_strictly_less + 0.5 * count_equal) / len(clean_peers)
    """
    if value is None:
        return None
    clean = [float(p) for p in peers if p is not None]
    if len(clean) < 3:
        return None
    v = float(value)
    count_less = sum(1 for p in clean if p < v)
    count_equal = sum(1 for p in clean if p == v)
    return (count_less + 0.5 * count_equal) / len(clean)


def peer_universe_id(sector: Optional[str], industry: Optional[str]) -> Optional[str]:
    if not sector or not industry:
        return None
    return f"sector:{sector}|industry:{industry}"


def build_peer_pct_table(
    target_facts: Dict[str, Optional[float]],
    peer_facts: List[Dict[str, Optional[float]]],
    inverted_fields: Set[str],
) -> Dict[str, Optional[float]]:
    """For each fact, return percentile rank of target vs peers.

    `inverted_fields` flips the rank (low = good → high percentile). E.g. P/E and P/B.
    """
    out: Dict[str, Optional[float]] = {}
    keys = set()
    for f in peer_facts:
        keys.update(f.keys())
    keys.update(target_facts.keys())
    for k in keys:
        peers = [f.get(k) for f in peer_facts]
        pct = percentile_rank(target_facts.get(k), peers)
        if pct is not None and k in inverted_fields:
            pct = 1.0 - pct
        out[k] = pct
    return out


@dataclass
class CachedPeers:
    tickers: List[str]
    facts: Dict[str, Dict[str, Optional[float]]]
    written_at: float

    def is_fresh(self, ttl_hours: int) -> bool:
        return (time.time() - self.written_at) < ttl_hours * 3600


class PeerCache:
    """JSON-per-sector cache under <data_cache_dir>/peer_facts/."""

    def __init__(self, base_dir: Path):
        self._dir = Path(base_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, slug: str) -> Path:
        safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in slug)
        return self._dir / f"{safe}.json"

    def read(self, slug: str) -> Optional[CachedPeers]:
        p = self._path(slug)
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return CachedPeers(
            tickers=list(data.get("tickers") or []),
            facts=dict(data.get("facts") or {}),
            written_at=float(data.get("written_at") or 0.0),
        )

    def write(self, slug: str, tickers: List[str],
              facts: Dict[str, Dict[str, Optional[float]]]) -> None:
        payload = {"tickers": tickers, "facts": facts, "written_at": time.time()}
        self._path(slug).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def slug_for(self, sector: Optional[str], industry: Optional[str]) -> Optional[str]:
        if not sector or not industry:
            return None
        return f"{sector}__{industry}"


def slug_for_sector(sector: Optional[str], industry: Optional[str]) -> Optional[str]:
    """Convenience wrapper matching PeerCache.slug_for."""
    if not sector or not industry:
        return None
    return f"{sector}__{industry}"
