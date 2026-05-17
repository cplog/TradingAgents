"""Sector/industry catalog merge helpers."""

from api.dimensions.sector_industry_catalog import merge_coverage_with_catalog


def test_merge_coverage_with_catalog_fills_zeros_and_appends_orphans():
    catalog = [
        {"sector": "Technology", "industry": "Semiconductors"},
        {"sector": "Technology", "industry": "Software - Infrastructure"},
    ]
    aggregates = [
        {
            "sector": "Technology",
            "industry": "Semiconductors",
            "run_count": 3,
            "with_dimensions_count": 2,
            "with_commentary_count": 1,
            "latest_completed_at": "2026-05-01",
        },
        {
            "sector": "(unknown)",
            "industry": "Legacy",
            "run_count": 1,
            "with_dimensions_count": 0,
            "with_commentary_count": 0,
            "latest_completed_at": None,
        },
    ]
    out = merge_coverage_with_catalog(catalog, aggregates)
    assert len(out) == 3
    semi = next(r for r in out if r["industry"] == "Semiconductors")
    assert semi["run_count"] == 3
    sw = next(r for r in out if r["industry"] == "Software - Infrastructure")
    assert sw["run_count"] == 0
    legacy = next(r for r in out if r["industry"] == "Legacy")
    assert legacy["sector"] == "(unknown)"
