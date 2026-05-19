"""Regression: request bodies accept extended analyst IDs (not only core four)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.jobs import _coerce_analyst_ids
from api.models import AnalyzeRequest, BatchAnalyzeRequest, DEFAULT_ANALYST_ORDER


@pytest.mark.unit
def test_analyze_request_accepts_extended_analyst_ids():
    req = AnalyzeRequest.model_validate(
        {
            "ticker": "AAPL",
            "analysts": ["market", "hot_money", "policy", "lockup", "kronos"],
        }
    )
    assert req.analysts == ["market", "hot_money", "policy", "lockup", "kronos"]


@pytest.mark.unit
def test_batch_analyze_request_accepts_extended_analyst_ids():
    req = BatchAnalyzeRequest.model_validate(
        {
            "tickers": ["NVDA"],
            "analysts": ["fundamentals", "kronos", "news"],
        }
    )
    assert req.analysts == ["fundamentals", "kronos", "news"]


@pytest.mark.unit
def test_default_analyst_order_includes_all_pipeline_analysts():
    assert DEFAULT_ANALYST_ORDER == (
        "market",
        "social",
        "news",
        "fundamentals",
        "hot_money",
        "policy",
        "lockup",
        "kronos",
    )


@pytest.mark.unit
def test_coerce_analyst_ids_none_uses_full_default_order():
    assert _coerce_analyst_ids(None) == list(DEFAULT_ANALYST_ORDER)


@pytest.mark.unit
def test_analyze_request_rejects_unknown_analyst_ids():
    with pytest.raises(ValidationError) as excinfo:
        AnalyzeRequest.model_validate({"ticker": "X", "analysts": ["market", "not_a_real_analyst"]})
    assert "Unknown analyst id" in str(excinfo.value)


@pytest.mark.unit
def test_analyze_request_normalizes_analyst_case():
    req = AnalyzeRequest.model_validate(
        {"ticker": "MSFT", "analysts": ["Hot_Money", "KRONOS"]}
    )
    assert req.analysts == ["hot_money", "kronos"]
