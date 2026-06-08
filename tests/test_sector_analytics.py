"""Tests for sector analytics aggregation helpers."""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from api.history import (
    _latest_per_ticker,
    _compute_rating_score,
    _compute_factor_score,
    _compute_freshness_score,
    _compute_bloom_signal,
    compute_sector_analytics,
    _FACTOR_SCORE_KEYS,
    _RATING_ORDER,
)


def make_run(
    ticker: str,
    rating: str = "Hold",
    confidence: float = 50.0,
    completed_at: str | None = None,
    factor_scores: dict | None = None,
    has_dimensions: bool = False,
    has_commentary: bool = False,
    run_id: str | None = None,
) -> dict:
    if completed_at is None:
        completed_at = datetime.now(timezone.utc).isoformat()
    row = {
        "ticker": ticker,
        "rating": rating,
        "confidence": confidence,
        "completed_at": completed_at,
        "has_dimensions": has_dimensions,
        "has_commentary": has_commentary,
        "run_id": run_id or f"run-{ticker}",
        "job_id": f"job-{ticker}",
        "trade_date": "2026-06-01",
        "factor_scores_json": json.dumps(factor_scores or {}),
        "facts_sector": "Technology",
        "facts_industry": "Semiconductors",
        "provenance_json": None,
    }
    return row


# ── _latest_per_ticker ──


def test_latest_per_ticker_dedup():
    rows = [
        make_run("AAPL", completed_at="2026-06-01T00:00:00Z"),
        make_run("AAPL", completed_at="2026-06-05T00:00:00Z"),
        make_run("MSFT", completed_at="2026-06-03T00:00:00Z"),
    ]
    out = _latest_per_ticker(rows)
    assert len(out) == 2
    assert out[0]["ticker"] == "AAPL" or out[1]["ticker"] == "AAPL"
    aapl = next(r for r in out if r["ticker"] == "AAPL")
    assert aapl["completed_at"] == "2026-06-05T00:00:00Z"


def test_latest_per_ticker_empty():
    assert _latest_per_ticker([]) == []


def test_latest_per_ticker_no_ticker_skipped():
    rows = [{"ticker": "", "completed_at": "2026-06-01T00:00:00Z"}]
    assert _latest_per_ticker(rows) == []


# ── _compute_rating_score ──


def test_rating_score_all_buy():
    dist = [
        {"rating": "Buy", "count": 5, "pct": 100.0},
        {"rating": "Overweight", "count": 0, "pct": 0.0},
        {"rating": "Hold", "count": 0, "pct": 0.0},
        {"rating": "Underweight", "count": 0, "pct": 0.0},
        {"rating": "Sell", "count": 0, "pct": 0.0},
    ]
    assert _compute_rating_score(dist) == 100.0


def test_rating_score_all_sell():
    dist = [
        {"rating": "Buy", "count": 0, "pct": 0.0},
        {"rating": "Overweight", "count": 0, "pct": 0.0},
        {"rating": "Hold", "count": 0, "pct": 0.0},
        {"rating": "Underweight", "count": 0, "pct": 0.0},
        {"rating": "Sell", "count": 5, "pct": 100.0},
    ]
    assert _compute_rating_score(dist) == 0.0


def test_rating_score_mixed():
    dist = [
        {"rating": "Buy", "count": 2, "pct": 0.0},
        {"rating": "Overweight", "count": 1, "pct": 0.0},
        {"rating": "Hold", "count": 1, "pct": 0.0},
        {"rating": "Underweight", "count": 0, "pct": 0.0},
        {"rating": "Sell", "count": 0, "pct": 0.0},
    ]
    # (2*100 + 1*75 + 1*50) / 4 = 325/4 = 81.25
    assert _compute_rating_score(dist) == 81.25


def test_rating_score_no_runs():
    dist = [{"rating": r, "count": 0, "pct": 0.0} for r in _RATING_ORDER]
    assert _compute_rating_score(dist) == 0.0


# ── _compute_factor_score ──


def test_factor_score_average():
    medians = [
        {"factor": "value", "median": 80.0, "tickers_with_data": 3},
        {"factor": "growth", "median": 60.0, "tickers_with_data": 4},
        {"factor": "quality", "median": 70.0, "tickers_with_data": 5},
        {"factor": "momentum", "median": 0.0, "tickers_with_data": 0},
        {"factor": "low_risk", "median": 0.0, "tickers_with_data": 0},
        {"factor": "sentiment", "median": 0.0, "tickers_with_data": 0},
    ]
    # averages ALL medians including zeros: (80+60+70+0+0+0)/6 = 35
    assert _compute_factor_score(medians) == 35.0


def test_factor_score_all_zero():
    medians = [
        {"factor": f, "median": 0.0, "tickers_with_data": 0} for f in _FACTOR_SCORE_KEYS
    ]
    assert _compute_factor_score(medians) == 0.0


def test_factor_score_empty():
    assert _compute_factor_score([]) == 0.0


# ── _compute_freshness_score ──


def test_freshness_score_fresh():
    now = datetime.now(timezone.utc).isoformat()
    score = _compute_freshness_score(now, 10, 10, [now])
    # fresh_score near 100, coverage_score = 100
    # 0.6 * 100 + 0.4 * 100 = 100
    assert score > 95


def test_freshness_score_stale():
    now = datetime.now(timezone.utc).isoformat()
    old = "2025-01-01T00:00:00+00:00"
    score = _compute_freshness_score(now, 10, 10, [old])
    # median days ~520 -> fresh_score = max(0, 100 - 520*2) = 0
    # coverage_score = 100
    # 0.6*0 + 0.4*100 = 40
    assert score == 40.0


def test_freshness_score_no_coverage():
    now = datetime.now(timezone.utc).isoformat()
    score = _compute_freshness_score(now, 0, 10, [now])
    # coverage_score = 0, fresh_score ~ 100
    # 0.6*100 + 0.4*0 = 60
    assert pytest.approx(score, abs=5) == 60


# ── _compute_bloom_signal ──


def test_bloom_insufficient_data():
    rows = [make_run("AAPL")]
    result = _compute_bloom_signal(rows)
    assert result["bloom_label"] == "Insufficient Data"
    assert result["bloom_score"] == 0


def test_bloom_emerging_with_recent_activity():
    now = datetime.now(timezone.utc)
    rows = []
    for i, tkr in enumerate(["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]):
        rows.append(make_run(
            tkr,
            completed_at=now.isoformat(),
            rating="Buy" if i < 3 else "Hold",
            factor_scores={"momentum": 65 if i < 3 else 55},
        ))
    # Also add 2 older runs to avoid insufficient_data
    for tkr in ["INTC", "AMD"]:
        rows.append(make_run(tkr, completed_at="2025-06-01T00:00:00Z"))
    for tkr in ["AAPL", "MSFT"]:
        rows.append(make_run(
            tkr,
            completed_at="2025-06-01T00:00:00Z",
            rating="Hold",
            factor_scores={"momentum": 40},
        ))
    result = _compute_bloom_signal(rows)
    assert result["bloom_label"] in ("Hot", "Accelerating", "Emerging")
    assert result["bloom_score"] >= 10


def test_bloom_recent_activity_growth():
    now = datetime.now(timezone.utc)
    rows = []
    # 3 recent tickers
    for tkr in ["AAPL", "MSFT", "NVDA"]:
        rows.append(make_run(tkr, completed_at=now.isoformat(), rating="Buy"))
    # 1 prior ticker
    for tkr in ["INTC"]:
        rows.append(make_run(tkr, completed_at="2026-05-20T00:00:00Z", rating="Hold"))
    # Add older runs so we have more than 3 total
    for tkr in ["AMD", "GOOGL"]:
        rows.append(make_run(tkr, completed_at="2025-01-01T00:00:00Z", rating="Sell"))
    result = _compute_bloom_signal(rows)
    assert result["bloom_label"] != "Insufficient Data"


# ── compute_sector_analytics with mocked D1 ──

def test_compute_sector_analytics_requires_d1(monkeypatch):
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: False)
    with pytest.raises(RuntimeError, match="d1_not_configured"):
        compute_sector_analytics(sector="Technology", industry="Semiconductors")


def test_compute_sector_analytics_empty_d1(monkeypatch):
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: True)
    monkeypatch.setattr("api.history._ensure_d1_schema", lambda: None)
    monkeypatch.setattr("api.history._d1_query", lambda sql, params=None, timeout=None: [])

    result = compute_sector_analytics(sector="Technology", industry="Semiconductors")
    assert result["sector"] == "Technology"
    assert result["industry"] == "Semiconductors"
    assert result["health_score"] == 0
    assert all(b["count"] == 0 for b in result["rating_distribution"])
    assert result["coverage_quality"]["analyzed_tickers"] == 0


def test_compute_sector_analytics_with_data(monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    fake_rows = [
        make_run("AAPL", rating="Buy", confidence=85.0, completed_at=now,
                 factor_scores={"value": 80, "growth": 75, "quality": 90, "momentum": 70, "low_risk": 60, "sentiment": 85},
                 has_dimensions=True, has_commentary=True, run_id="run-aapl"),
        make_run("MSFT", rating="Overweight", confidence=70.0, completed_at=now,
                 factor_scores={"value": 75, "growth": 80, "quality": 85, "momentum": 65, "low_risk": 55, "sentiment": 80},
                 has_dimensions=True, has_commentary=False, run_id="run-msft"),
        make_run("NVDA", rating="Buy", confidence=90.0, completed_at=now,
                 factor_scores={"value": 95, "growth": 90, "quality": 80, "momentum": 85, "low_risk": 40, "sentiment": 90},
                 has_dimensions=True, has_commentary=True, run_id="run-nvda"),
    ]

    monkeypatch.setattr("api.history.d1_history_enabled", lambda: True)
    monkeypatch.setattr("api.history._ensure_d1_schema", lambda: None)

    call_count = 0

    def fake_query(sql: str, params=None, timeout=None):
        nonlocal call_count
        call_count += 1
        return fake_rows

    monkeypatch.setattr("api.history._d1_query", fake_query)

    result = compute_sector_analytics(
        sector="Technology", industry="Semiconductors", total_constituents=10
    )

    assert result["sector"] == "Technology"
    assert result["industry"] == "Semiconductors"
    assert result["health_score"] > 0

    # Rating distribution: 2 Buy, 1 Overweight
    buy_bucket = next(b for b in result["rating_distribution"] if b["rating"] == "Buy")
    assert buy_bucket["count"] == 2
    ow_bucket = next(b for b in result["rating_distribution"] if b["rating"] == "Overweight")
    assert ow_bucket["count"] == 1

    # Factor medians
    assert len(result["factor_medians"]) == 6
    value_f = next(f for f in result["factor_medians"] if f["factor"] == "value")
    assert value_f["median"] == 80.0
    assert value_f["tickers_with_data"] == 3

    # Coverage
    assert result["coverage_quality"]["analyzed_tickers"] == 3
    assert result["coverage_quality"]["total_constituents"] == 10
    assert result["coverage_quality"]["pct_with_dimensions"] == 100.0

    # Avg confidence
    assert result["avg_confidence"] > 0

    # Bloom signal
    assert "bloom" in result
