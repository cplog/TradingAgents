"""History persistence — dimensions in run record + recompute endpoint."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.history import get_run, list_runs, persist_completed_run
from api.main import app
from api.state_store import LocalFileStateStore


@pytest.fixture
def store(tmp_path):
    return LocalFileStateStore(path=tmp_path / "state.json")


def test_persist_run_with_dimensions_round_trips(store):
    result = {
        "ticker": "AAPL",
        "date": "2026-05-13",
        "rating": "Buy",
        "confidence": 0.9,
        "reports": {"market": "x"},
        "completed_at": "2026-05-13T00:00:00Z",
        "dimensions": {
            "ticker": "AAPL",
            "as_of_date": "2026-05-13",
            "factor_scores": {"value": {"score": 70.0, "inputs": {}}},
        },
        "dimensions_commentary": {
            "alignment": "aligned",
            "summary": "ok",
            "supporting_dimensions": ["value"],
            "conflicting_dimensions": [],
            "risk_flags": [],
        },
    }
    persist_completed_run(
        store,
        job_id="job1",
        ticker="AAPL",
        date="2026-05-13",
        result=result,
        created_at=datetime.utcnow(),
    )
    rec = get_run(store, "job1")
    assert rec is not None
    assert rec["dimensions"]["factor_scores"]["value"]["score"] == 70.0
    assert rec["dimensions_commentary"]["alignment"] == "aligned"


def test_list_runs_includes_factor_scores_in_ref(store):
    result = {
        "ticker": "AAPL",
        "date": "2026-05-13",
        "rating": "Buy",
        "reports": {},
        "completed_at": "2026-05-13T00:00:00Z",
        "dimensions": {
            "ticker": "AAPL",
            "as_of_date": "2026-05-13",
            "factor_scores": {
                "value": {"score": 70.0, "inputs": {}},
                "growth": {"score": 60.0, "inputs": {}},
                "quality": {"score": 80.0, "inputs": {}},
                "momentum": {"score": 55.0, "inputs": {}},
                "low_risk": {"score": 40.0, "inputs": {}},
                "sentiment": {"score": 50.0, "inputs": {}},
            },
        },
    }
    persist_completed_run(
        store,
        job_id="job2",
        ticker="AAPL",
        date="2026-05-13",
        result=result,
        created_at=datetime.utcnow(),
    )
    rows = list_runs(store, ticker="AAPL", limit=10)
    assert len(rows) >= 1
    row = rows[0]
    assert row.get("factor_scores", {}).get("value") == 70.0


def test_recompute_dimensions_endpoint(monkeypatch, store, tmp_path):
    # Pre-populate a run with no dimensions
    result = {
        "ticker": "AAPL",
        "date": "2026-05-13",
        "rating": "Buy",
        "reports": {
            "market": "m",
            "social": "s",
            "news": "n",
            "fundamentals": "f",
            "portfolio_decision": "Buy.",
        },
        "completed_at": "2026-05-13T00:00:00Z",
    }
    persist_completed_run(
        store,
        job_id="job3",
        ticker="AAPL",
        date="2026-05-13",
        result=result,
        created_at=datetime.utcnow(),
    )

    monkeypatch.setattr("api.main.get_state_store", lambda: store)

    # Stub the builders so we don't touch yfinance/LLM
    from api.dimensions.schemas import (
        DimensionsCommentary,
        FactorScore,
        FactorScores,
        FactSnapshot,
        FundamentalsPillar,
        MarketPillar,
        NewsPillar,
        PillarScore,
        PillarScores,
        SentimentPillar,
        StockDimensions,
    )

    def _ps():
        return PillarScore(score=3, rationale="x")

    fake_dim = StockDimensions(
        ticker="AAPL",
        as_of_date="2026-05-13",
        facts=FactSnapshot(as_of_date="2026-05-13", currency="USD"),
        pillar_scores=PillarScores(
            market=MarketPillar(
                trend=_ps(),
                momentum=_ps(),
                volatility_risk=_ps(),
                setup_quality=_ps(),
            ),
            sentiment=SentimentPillar(
                retail_sentiment=_ps(),
                social_buzz=_ps(),
                consensus_quality=_ps(),
                narrative_strength=_ps(),
            ),
            news=NewsPillar(
                catalyst_strength=_ps(),
                macro_alignment=_ps(),
                headline_quality=_ps(),
                surprise_risk=_ps(),
            ),
            fundamentals=FundamentalsPillar(
                valuation=_ps(),
                growth=_ps(),
                profitability=_ps(),
                balance_sheet_strength=_ps(),
            ),
        ),
        factor_scores=FactorScores(
            value=FactorScore(score=70.0),
            growth=FactorScore(score=60.0),
            quality=FactorScore(score=80.0),
            momentum=FactorScore(score=55.0),
            low_risk=FactorScore(score=40.0),
            sentiment=FactorScore(score=50.0),
        ),
        dimensions_version="1.0.0",
    )
    fake_comm = DimensionsCommentary(
        alignment="aligned",
        supporting_dimensions=["value"],
        conflicting_dimensions=[],
        risk_flags=[],
        summary="ok",
    )
    monkeypatch.setattr("api.main.build_dimensions", lambda **k: fake_dim)
    monkeypatch.setattr(
        "api.main.build_commentary_orchestrator", lambda **k: fake_comm
    )
    # Stub the LLM factory
    monkeypatch.setattr("api.main._build_llm_for_dimensions", lambda cfg: MagicMock())

    client = TestClient(app)
    r = client.post("/history/runs/job3/recompute-dimensions")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dimensions"]["factor_scores"]["value"]["score"] == 70.0
