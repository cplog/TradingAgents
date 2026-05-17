"""Tiered peer resolution against on-disk caches (no D1)."""

from pathlib import Path

import pytest

from api.dimensions.facts import FactSnapshot
from api.dimensions.peer_resolver import resolve_peer_facts_for_snapshot
from api.dimensions.peers import (
    PeerCache,
    market_bucket_from_exchange_currency,
    slug_for_local_industry_universe,
    slug_for_sector,
)


def _row(**kwargs):
    base = dict(
        pe_ttm=20.0, pb=2.0, eps_growth_yoy=0.05, revenue_growth_yoy=0.03,
        roe=0.10, interest_coverage=5.0, return_3m=0.01, return_12m=0.05, beta=1.05,
    )
    base.update(kwargs)
    return base


@pytest.fixture(autouse=True)
def no_d1(monkeypatch):
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: False)


def test_resolver_prefers_local_market_slug(tmp_path):
    facts = FactSnapshot(
        as_of_date="2026-05-14",
        currency="HKD",
        exchange="HKG",
        sector="Financial Services",
        industry="Insurance - Life",
    )
    mb = market_bucket_from_exchange_currency(facts.exchange, facts.currency)
    assert mb == "HKG.HKD"
    slug = slug_for_local_industry_universe(mb, facts.sector, facts.industry)
    assert slug is not None

    fm = {"T1": _row(pe_ttm=10), "T2": _row(pe_ttm=15), "T3": _row(pe_ttm=30)}
    cache_dir = tmp_path / "peer_facts"
    cache_dir.mkdir(parents=True)
    PeerCache(cache_dir).write(slug, list(fm.keys()), fm)

    out = resolve_peer_facts_for_snapshot(facts, cache_dir)
    assert out.peer_scope == "local"
    assert out.peer_row_count == 3
    assert out.slug_used == slug


def test_resolver_falls_back_to_global_sector_slug(tmp_path):
    facts = FactSnapshot(
        as_of_date="2026-05-13",
        currency="USD",
        exchange="NMS",
        sector="Technology",
        industry="Consumer Electronics",
    )
    mb = market_bucket_from_exchange_currency(facts.exchange, facts.currency)
    local_slug = slug_for_local_industry_universe(mb, facts.sector, facts.industry)
    global_slug = slug_for_sector(facts.sector, facts.industry)

    fm = {"A": _row(), "B": _row(pe_ttm=22), "C": _row(pe_ttm=24)}
    cache_dir = tmp_path / "pf"
    cache_dir.mkdir(parents=True)
    assert local_slug != global_slug
    PeerCache(cache_dir).write(global_slug, list(fm.keys()), fm)

    out = resolve_peer_facts_for_snapshot(facts, Path(cache_dir))
    assert out.peer_scope == "global_fallback"
    assert "peer_scope_global_fallback" in out.escalation_flags
    assert out.slug_used == global_slug


def test_resolver_unavailable_when_all_missing(tmp_path):
    facts = FactSnapshot(as_of_date="2026-05-13", currency="USD", sector="Technology",
                         industry="Consumer Electronics")
    out = resolve_peer_facts_for_snapshot(facts, tmp_path / "missing")
    assert out.peer_scope == "unavailable"
    assert out.peer_row_count == 0
