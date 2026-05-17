"""D1 upsert helpers for Yahoo sector/industry cold start."""

from unittest.mock import MagicMock

import pytest

from api.dimensions.sector_industry_catalog import (
    cold_start_yahoo_sectors_to_d1,
    upsert_yahoo_catalog_to_d1,
)


def test_upsert_yahoo_catalog_to_d1_calls_conflict_sql(monkeypatch):
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: True)
    monkeypatch.setattr("api.history._ensure_d1_schema", lambda: None)
    captured: list[tuple[str, list]] = []

    def fake_query(sql: str, params=None):
        captured.append((sql, params or []))
        return []

    monkeypatch.setattr("api.history._d1_query", fake_query)

    stats = upsert_yahoo_catalog_to_d1(
        [{"sector": "Technology", "industry": "Semiconductors", "industry_key": "semiconductors"}],
        constituent_rows=[
            {
                "sector": "Technology",
                "industry": "Semiconductors",
                "industry_key": "semiconductors",
                "market": "US",
                "ticker": "NVDA",
            },
            {
                "sector": "Technology",
                "industry": "Semiconductors",
                "industry_key": "semiconductors",
                "market": "HK",
                "ticker": "0700.HK",
            },
        ],
    )
    assert stats["buckets"] == 1
    assert stats["constituents"] == 2
    assert any("ON CONFLICT" in sql for sql, _ in captured)
    assert any("yahoo_sector_industry_buckets" in sql for sql, _ in captured)
    assert any("yahoo_industry_constituents" in sql for sql, _ in captured)


def test_cold_start_batches_fetch_and_upsert(monkeypatch):
    entries = [
        {
            "sector": "Technology",
            "industry": "Semiconductors",
            "industry_key": "semiconductors",
        }
    ]
    monkeypatch.setattr(
        "api.dimensions.sector_industry_catalog.fetch_yahoo_catalog_entries",
        lambda: entries,
    )
    monkeypatch.setattr(
        "api.dimensions.sector_industry_catalog.fetch_yahoo_industry_constituents",
        lambda key: ["NVDA"] if key == "semiconductors" else [],
    )
    upsert = MagicMock(return_value={"buckets": 1, "constituents": 1})
    monkeypatch.setattr(
        "api.dimensions.sector_industry_catalog.upsert_yahoo_catalog_to_d1",
        upsert,
    )

    stats = cold_start_yahoo_sectors_to_d1(fetch_constituents=True, markets=["US"])
    assert stats["buckets"] == 1
    upsert.assert_called_once()
    rows = upsert.call_args.kwargs["constituent_rows"]
    assert len(rows) == 1
    assert rows[0]["ticker"] == "NVDA"
    assert rows[0]["market"] == "US"


def test_upsert_requires_d1(monkeypatch):
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: False)
    with pytest.raises(RuntimeError, match="D1 is not configured"):
        upsert_yahoo_catalog_to_d1([])
