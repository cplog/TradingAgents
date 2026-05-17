"""Resolve cached peer facts for dimensions with local-market priority + global fallback."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from api.dimensions.facts import FactSnapshot
from api.dimensions.peer_store import load_peer_facts_for_slug
from api.dimensions.peers import (
    market_bucket_from_exchange_currency,
    peer_universe_id,
    peer_universe_label_local,
    peer_universe_label_local_sector_group,
    slug_for_local_industry_universe,
    slug_for_local_sector_universe,
    slug_for_sector,
)

PeerScope = Literal["local", "local_sector", "global_fallback", "unavailable"]

_TIER = Tuple[str, str, PeerScope]


@dataclass
class PeerFactsResolution:
    """Outcome of resolving which peer universe to use for percentile ranking."""

    facts_by_ticker: Dict[str, Dict[str, Any]]
    slug_used: Optional[str]
    peer_scope: PeerScope
    peer_universe_label: Optional[str]
    search_path_labels: List[str] = field(default_factory=list)
    escalation_flags: List[str] = field(default_factory=list)

    @property
    def peer_row_count(self) -> int:
        return len(self.facts_by_ticker)


def _facts_dict_normalize(
    raw: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Keep JSON-serializable dicts usable for percentile math (numeric facts only kept)."""
    out: Dict[str, Dict[str, Any]] = {}
    for ticker, blob in raw.items():
        fd: Dict[str, Any] = {}
        if not isinstance(blob, dict):
            continue
        for key, val in blob.items():
            if val is None or isinstance(val, bool):
                fd[key] = None
            elif isinstance(val, (int, float)):
                fd[key] = float(val)
            else:
                fd[key] = None
        out[str(ticker)] = fd
    return out


def _build_candidate_tiers(facts: FactSnapshot) -> Tuple[List[_TIER], Optional[str]]:
    """Return tier list (slug, label, scope) and market bucket."""
    tiers: List[_TIER] = []
    mb = market_bucket_from_exchange_currency(facts.exchange, facts.currency)

    if mb and facts.sector and facts.industry:
        slug_li = slug_for_local_industry_universe(mb, facts.sector, facts.industry)
        if slug_li:
            tiers.append((
                slug_li,
                peer_universe_label_local(mb, facts.sector, facts.industry),
                "local",
            ))

    if mb and facts.sector:
        slug_ls = slug_for_local_sector_universe(mb, facts.sector)
        if slug_ls:
            tiers.append((
                slug_ls,
                peer_universe_label_local_sector_group(mb, facts.sector),
                "local_sector",
            ))

    if facts.sector and facts.industry:
        slug_g = slug_for_sector(facts.sector, facts.industry)
        lbl_g = peer_universe_id(facts.sector, facts.industry)
        if slug_g and lbl_g:
            tiers.append((slug_g, lbl_g, "global_fallback"))

    return tiers, mb


def _tier_escalation_flags(
    tiers: List[_TIER],
    winner_index: int,
    winner_scope: PeerScope,
    had_market_bucket: bool,
) -> List[str]:
    flags: List[str] = []
    if winner_scope == "global_fallback":
        flags.append("peer_scope_global_fallback")
        if had_market_bucket:
            flags.append("peer_escalated_beyond_home_market")

    if winner_scope == "local_sector":
        local_industry_tier_present = tiers and tiers[0][2] == "local"
        if local_industry_tier_present and winner_index >= 1:
            flags.append("peer_escalated_from_industry_to_sector_within_market")

    return flags


def resolve_peer_facts_for_snapshot(
    facts: FactSnapshot,
    peer_facts_dir: Path,
) -> PeerFactsResolution:
    tiers, mb = _build_candidate_tiers(facts)
    search_labels = [t[1] for t in tiers]

    if not tiers:
        return PeerFactsResolution(
            {},
            None,
            "unavailable",
            None,
            search_labels,
            ["peer_percentiles_cache_miss"],
        )

    winner_index = -1
    chosen_slug: Optional[str] = None
    chosen_label: Optional[str] = None
    chosen_scope: PeerScope = "unavailable"
    chosen_raw: Dict[str, Dict[str, Any]] = {}

    for i, (slug, label, scope) in enumerate(tiers):
        raw, _ = load_peer_facts_for_slug(slug, peer_facts_dir)
        if len(raw) >= 3:
            chosen_raw = raw
            winner_index = i
            chosen_slug = slug
            chosen_label = label
            chosen_scope = scope
            break

    if winner_index < 0:
        return PeerFactsResolution(
            {}, None, "unavailable", None, search_labels, ["peer_percentiles_cache_miss"],
        )

    esc = _tier_escalation_flags(tiers, winner_index, chosen_scope, bool(mb))

    return PeerFactsResolution(
        facts_by_ticker=_facts_dict_normalize(chosen_raw),
        slug_used=chosen_slug,
        peer_scope=chosen_scope,
        peer_universe_label=chosen_label,
        search_path_labels=search_labels,
        escalation_flags=esc,
    )


def peer_universe_display_label(res: PeerFactsResolution) -> Optional[str]:
    """UX label: resolved universe, else the first comparison universe we attempted."""
    if res.peer_universe_label:
        return res.peer_universe_label
    if res.search_path_labels:
        return res.search_path_labels[0]
    return None
