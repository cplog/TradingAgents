"""Sector/industry coverage and filtered history listing (D1-oriented)."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.history import list_history_coverage, list_runs
from api.main import app


def test_coverage_endpoint_without_d1_returns_catalog(monkeypatch):
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: False)
    monkeypatch.setattr(
        "api.dimensions.sector_industry_catalog.load_sector_industry_catalog",
        lambda *a, **k: [
            {"sector": "Technology", "industry": "Semiconductors"},
        ],
    )
    c = TestClient(app)
    r = c.get("/api/history/coverage")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["run_count"] == 0


def test_list_runs_sector_filter_requires_d1(monkeypatch):
    monkeypatch.setattr("api.main.d1_history_enabled", lambda: False)
    c = TestClient(app)
    r = c.get("/api/history/runs", params={"sector": "Technology"})
    assert r.status_code == 501


def test_list_history_coverage_returns_rows(monkeypatch):
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: True)

    fake_rows = [
        {
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "run_count": 3,
            "with_dimensions_count": 2,
            "with_commentary_count": 1,
            "latest_completed_at": "2026-05-01T00:00:00Z",
        }
    ]

    def fake_query(sql: str, params=None):
        return fake_rows if "GROUP BY" in sql.upper() else []

    monkeypatch.setattr("api.history._ensure_d1_schema", lambda: None)
    monkeypatch.setattr("api.history._d1_query", fake_query)
    monkeypatch.setattr(
        "api.dimensions.sector_industry_catalog.load_sector_industry_catalog",
        lambda *a, **k: [],
    )

    out = list_history_coverage()
    assert len(out) == 1
    assert out[0]["sector"] == "Technology"
    assert out[0]["run_count"] == 3


def test_list_history_coverage_merges_catalog_with_aggregates(monkeypatch):
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: True)

    fake_agg = [
        {
            "sector": "Technology",
            "industry": "Semiconductors",
            "run_count": 2,
            "with_dimensions_count": 2,
            "with_commentary_count": 1,
            "latest_completed_at": "2026-05-01T00:00:00Z",
        },
        {
            "sector": "(unknown)",
            "industry": "Mystery",
            "run_count": 1,
            "with_dimensions_count": 0,
            "with_commentary_count": 0,
            "latest_completed_at": None,
        },
    ]

    monkeypatch.setattr("api.history._list_history_coverage_aggregates", lambda: fake_agg)
    monkeypatch.setattr(
        "api.dimensions.sector_industry_catalog.load_sector_industry_catalog",
        lambda *a, **k: [
            {"sector": "Technology", "industry": "Semiconductors"},
            {"sector": "Technology", "industry": "Software - Infrastructure"},
        ],
    )

    out = list_history_coverage()
    assert len(out) == 3
    by_key = {(r["sector"], r["industry"]): r for r in out}
    assert by_key[("Technology", "Semiconductors")]["run_count"] == 2
    assert by_key[("Technology", "Software - Infrastructure")]["run_count"] == 0
    assert by_key[("(unknown)", "Mystery")]["run_count"] == 1


def test_list_runs_sector_filter_queries_d1(monkeypatch):
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: True)
    captured: list[tuple[str, object]] = []

    def fake_query(sql: str, params=None):
        captured.append((sql, params))
        return []

    monkeypatch.setattr("api.history._ensure_d1_schema", lambda: None)
    monkeypatch.setattr("api.history._d1_query", fake_query)

    list_runs(
        MagicMock(),
        ticker=None,
        limit=25,
        date_from=None,
        date_to=None,
        sector="Financial Services",
        industry="Insurance - Property",
    )

    assert captured, "expected D1 query"
    sql_text = captured[0][0]
    assert "json_extract(dimensions_json, '$.facts.sector')" in sql_text.lower()
    assert captured[0][1] is not None
    params = captured[0][1]
    assert isinstance(params, list)
    assert "Financial Services" in params
    assert "Insurance - Property" in params


def test_coverage_endpoint_returns_json(monkeypatch):
    monkeypatch.setattr("api.main.d1_history_enabled", lambda: True)

    def fake_coverage():
        return [
            {
                "sector": "A",
                "industry": "B",
                "run_count": 1,
                "with_dimensions_count": 1,
                "with_commentary_count": 0,
                "latest_completed_at": None,
            }
        ]

    monkeypatch.setattr("api.main.list_history_coverage", fake_coverage)

    c = TestClient(app)
    r = c.get("/api/history/coverage")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["sector"] == "A"


def test_list_runs_uses_kv_only_when_d1_disabled(monkeypatch):
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: False)

    fake_store = MagicMock()
    fake_store.get_json.return_value = [
        {
            "run_id": "job-1",
            "ticker": "AAPL",
            "date": "2026-05-01",
            "rating": "Hold",
        }
    ]

    rows = list_runs(
        fake_store,
        ticker=None,
        limit=10,
        date_from=None,
        date_to=None,
        sector=None,
        industry=None,
    )

    assert len(rows) == 1
    assert rows[0]["run_id"] == "job-1"


def test_list_runs_sector_filter_raises_without_d1(monkeypatch):
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: False)
    with pytest.raises(RuntimeError, match="sector_industry_filters_require_d1"):
        list_runs(
            MagicMock(),
            limit=10,
            sector="Technology",
            industry="Semiconductors",
        )


def test_constituents_endpoint_merges_catalog_and_runs(monkeypatch):
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: True)
    monkeypatch.setattr("api.history._ensure_d1_schema", lambda: None)

    def fake_query(sql: str, params=None):
        if "yahoo_industry_constituents" in sql:
            return [
                {"market": "US", "ticker": "NVDA"},
                {"market": "US", "ticker": "AMD"},
            ]
        return []

    monkeypatch.setattr("api.history._d1_query", fake_query)
    monkeypatch.setattr(
        "api.history._list_runs_d1",
        lambda **kwargs: [
            {
                "ticker": "NVDA",
                "run_id": "job-1",
                "date": "2026-05-01",
                "rating": "Hold",
                "has_dimensions": True,
                "has_commentary": False,
                "completed_at": "2026-05-01T12:00:00Z",
            },
        ],
    )

    c = TestClient(app)
    r = c.get(
        "/api/history/constituents",
        params={"sector": "Technology", "industry": "Semiconductors"},
    )
    assert r.status_code == 200
    body = r.json()
    by_ticker = {row["ticker"]: row for row in body}
    assert by_ticker["NVDA"]["has_report"] is True
    assert by_ticker["NVDA"]["has_dimensions"] is True
    assert by_ticker["AMD"]["has_report"] is False

    r_cat = c.get(
        "/api/catalog/industry-constituents",
        params={"sector": "Technology", "industry": "Semiconductors"},
    )
    assert r_cat.status_code == 200
    assert r_cat.json() == body


def test_constituents_falls_back_to_yahoo_when_d1_constituents_empty(monkeypatch):
    """Buckets may exist without yahoo_industry_constituents rows until cold-start."""
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: True)
    monkeypatch.setattr("api.history._ensure_d1_schema", lambda: None)

    def fake_query(sql: str, params=None):
        sql_l = sql.lower()
        if "from yahoo_industry_constituents" in sql_l:
            return []
        if "from yahoo_sector_industry_buckets" in sql_l:
            return [{"industry_key": "asset-management"}]
        return []

    monkeypatch.setattr("api.history._d1_query", fake_query)
    monkeypatch.setattr(
        "api.dimensions.sector_industry_catalog.fetch_yahoo_industry_constituents",
        lambda key: ["AB", "ZZZ"] if key == "asset-management" else [],
    )
    monkeypatch.setattr("api.history._list_runs_d1", lambda **kwargs: [])

    c = TestClient(app)
    r = c.get(
        "/api/history/constituents",
        params={"sector": "Financial Services", "industry": "Asset Management"},
    )
    assert r.status_code == 200, r.text
    tickers = {row["ticker"] for row in r.json()}
    assert tickers == {"AB", "ZZZ"}


def test_constituents_endpoint_requires_d1(monkeypatch):
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: False)
    c = TestClient(app)
    r = c.get(
        "/api/history/constituents",
        params={"sector": "Technology", "industry": "Semiconductors"},
    )
    assert r.status_code == 500
