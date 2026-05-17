"""Dimension peer universes: D1 when configured, else on-disk ``peer_facts/`` JSON only."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from api.dimensions.peers import PeerCache

logger = logging.getLogger(__name__)


def load_peer_facts_for_slug(
    slug: str,
    peer_facts_dir: Path,
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Return (ticker -> facts dict, tickers in stable order) for ``slug``."""
    from api.history import _d1_query, _ensure_d1_schema, d1_history_enabled

    if d1_history_enabled():
        _ensure_d1_schema()
        rows = _d1_query(
            "SELECT ticker, facts_json FROM dimension_peer_members WHERE slug = ?",
            [slug],
        )
        facts_out: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            ticker = row.get("ticker")
            raw_json = row.get("facts_json")
            if ticker and isinstance(raw_json, str):
                facts_out[str(ticker)] = json.loads(raw_json)
        return facts_out, list(facts_out.keys())

    cache = PeerCache(base_dir=peer_facts_dir)
    rec = cache.read(slug)
    if rec is None:
        return {}, []
    facts = dict(rec.facts or {})
    return facts, list(rec.tickers or facts.keys())


def persist_dimension_peer_universe(
    slug: str,
    *,
    scope: str,
    sector: str,
    industry: str,
    facts: Dict[str, Dict[str, Any]],
    exchange: Optional[str] = None,
    currency: Optional[str] = None,
) -> bool:
    """Upsert peers for ``slug`` into D1. Returns False if D1 is not configured.

    Replaces existing members under ``slug`` atomically-ish (DELETE + INSERT loops).
    """
    from api.history import _d1_query, _ensure_d1_schema, d1_history_enabled

    if not d1_history_enabled():
        return False

    now = time.time()
    try:
        _ensure_d1_schema()
        peer_count = len(facts or {})
        _d1_query("DELETE FROM dimension_peer_members WHERE slug = ?", [slug])
        for ticker, fact_dict in (facts or {}).items():
            _d1_query(
                """
                INSERT INTO dimension_peer_members
                    (slug, ticker, facts_json, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                [
                    slug,
                    str(ticker),
                    json.dumps(fact_dict, ensure_ascii=False),
                    now,
                ],
            )
        _d1_query(
            """
            INSERT INTO dimension_peer_universes (
                slug, scope, exchange, currency, sector, industry, peer_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                scope = excluded.scope,
                exchange = excluded.exchange,
                currency = excluded.currency,
                sector = excluded.sector,
                industry = excluded.industry,
                peer_count = excluded.peer_count,
                updated_at = excluded.updated_at
            """,
            [
                slug,
                scope,
                exchange,
                currency,
                sector,
                industry,
                peer_count,
                now,
            ],
        )
    except Exception:
        logger.exception("D1 peer persist failed slug=%s", slug)
        raise
    return True
