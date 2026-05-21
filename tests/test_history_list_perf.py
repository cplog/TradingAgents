"""Unit tests for D1 history list slim-index helpers."""

from __future__ import annotations

import pytest

from api.history import (
    _compact_factor_scores,
    _d1_list_row_to_ref,
    _list_index_fields_from_full,
)


@pytest.mark.unit
def test_compact_factor_scores_extracts_scores():
    dims = {
        "factor_scores": {
            "value": {"score": 0.7},
            "growth": {"score": 0.5},
            "quality": {"label": "ok"},
        }
    }
    assert _compact_factor_scores(dims) == {"value": 0.7, "growth": 0.5}


@pytest.mark.unit
def test_list_index_fields_from_full_includes_provenance_json():
    full = {
        "dimensions": {
            "facts": {"sector": "Technology", "industry": "Software"},
            "factor_scores": {"momentum": {"score": 0.9}},
        },
        "config_snapshot": {"llm_provider": "openai", "deep_think_llm": "gpt-5"},
        "analyst_coverage": {"market": {"status": "ok"}},
    }
    fields = _list_index_fields_from_full(full)
    assert fields["facts_sector"] == "Technology"
    assert fields["facts_industry"] == "Software"
    assert fields["factor_scores_json"] is not None
    assert "openai" in (fields["provenance_json"] or "")


@pytest.mark.unit
def test_d1_list_row_to_ref_without_large_json_columns():
    ref = _d1_list_row_to_ref(
        {
            "run_id": "abc123",
            "job_id": "abc123",
            "ticker": "AAPL",
            "trade_date": "2026-05-01",
            "rating": "Buy",
            "confidence": 0.8,
            "completed_at": "2026-05-01T12:00:00Z",
            "created_at": "2026-05-01T11:00:00Z",
            "batch_id": None,
            "factor_scores_json": '{"value": 0.6}',
            "facts_sector": "Technology",
            "facts_industry": "Software",
            "provenance_json": '{"llm_provider": "openai", "deep_think_llm": "gpt-5", "quick_think_llm": "gpt-5-mini", "data_routing_label": "yfinance", "analysts": ["market"], "bias_warnings": []}',
            "has_dimensions": 1,
            "has_commentary": 0,
        }
    )
    assert ref["run_id"] == "abc123"
    assert ref["factor_scores"]["value"] == 0.6
    assert ref["facts_sector"] == "Technology"
    assert ref["provenance"]["llm_provider"] == "openai"
