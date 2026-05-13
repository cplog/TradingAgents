import json
import time
from pathlib import Path

import pytest

from api.dimensions.peers import (
    PeerCache, percentile_rank, build_peer_pct_table, peer_universe_id,
)


def test_percentile_rank_basic():
    values = [10, 20, 30, 40, 50]
    assert percentile_rank(30, values) == pytest.approx(0.5)
    assert percentile_rank(10, values) == pytest.approx(0.1)
    assert percentile_rank(50, values) == pytest.approx(0.9)


def test_percentile_rank_handles_none_and_short_list():
    assert percentile_rank(None, [1, 2, 3]) is None
    assert percentile_rank(5, [1]) is None  # fewer than 3 peers
    assert percentile_rank(5, [1, 2]) is None


def test_percentile_rank_drops_none_peers():
    values = [10, None, 30, None, 50]
    assert percentile_rank(30, values) == pytest.approx(0.5)


def test_peer_universe_id_includes_sector_industry():
    assert peer_universe_id("Technology", "Software-Infrastructure") == \
           "sector:Technology|industry:Software-Infrastructure"
    assert peer_universe_id(None, "X") is None


def test_peer_cache_round_trip(tmp_path):
    cache = PeerCache(base_dir=tmp_path)
    cache.write("sector_tech", ["AAPL", "MSFT", "NVDA"], {"AAPL": {"pe_ttm": 28.0}})
    rec = cache.read("sector_tech")
    assert rec is not None
    assert rec.tickers == ["AAPL", "MSFT", "NVDA"]
    assert rec.facts["AAPL"]["pe_ttm"] == 28.0
    assert rec.is_fresh(ttl_hours=24)


def test_peer_cache_stale_detection(tmp_path):
    cache = PeerCache(base_dir=tmp_path)
    cache.write("sector_x", ["A", "B"], {})
    rec = cache.read("sector_x")
    # Backdate
    rec_path = tmp_path / "sector_x.json"
    data = json.loads(rec_path.read_text())
    data["written_at"] = data["written_at"] - 25 * 3600
    rec_path.write_text(json.dumps(data))
    rec2 = cache.read("sector_x")
    assert not rec2.is_fresh(ttl_hours=24)


def test_build_peer_pct_table_inverted_for_value_metrics():
    peer_facts = [
        {"pe_ttm": 10.0, "pb": 1.0},
        {"pe_ttm": 20.0, "pb": 2.0},
        {"pe_ttm": 30.0, "pb": 3.0},
        {"pe_ttm": 40.0, "pb": 4.0},
        {"pe_ttm": 50.0, "pb": 5.0},
    ]
    target = {"pe_ttm": 15.0, "pb": 1.5}
    table = build_peer_pct_table(target, peer_facts, inverted_fields={"pe_ttm", "pb"})
    # pe_ttm 15 ranks 2nd lowest out of 6 → low PE is good → inverted percentile high
    assert table["pe_ttm"] > 0.6
    assert table["pb"] > 0.6
