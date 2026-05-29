"""Live context API endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.state_store import reset_state_store_for_tests


class _FakeGraph:
    def __init__(self, **kwargs):
        pass

    def propagate(self, ticker, date):
        return (
            {
                "market_report": "## Market\nOK",
                "investment_debate_state": {"judge_decision": "## RM\nPlan"},
                "risk_debate_state": {"judge_decision": "## PM\n**Buy**"},
            },
            "Buy",
        )


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder")
    monkeypatch.setenv("TRADINGAGENTS_API_STATE_FILE", str(tmp_path / "api_state.json"))
    reset_state_store_for_tests()
    monkeypatch.setattr("api.jobs.TradingAgentsGraph", _FakeGraph)

    from api.main import app

    with TestClient(app) as client:
        yield client


@pytest.mark.unit
def test_live_context_returns_comparison(api_client: TestClient, monkeypatch):
    from api import main
    from tradingagents.agents.utils import execution_context as ec

    monkeypatch.setattr(
        ec,
        "build_live_context_payload",
        lambda ticker, trade_date, reports, **kwargs: {
            "quote": {
                "ticker": ticker,
                "price": 13.1,
                "currency": "USD",
                "fetched_at": "2026-05-29T00:00:00Z",
                "source": "yfinance_regularMarketPrice",
                "error": None,
            },
            "report_close": 15.0,
            "trade_date": trade_date,
            "levels": {"entry": 15.1, "stop_loss": 14.8, "price_target": 16.8},
            "comparison": {
                "status": "below_stop",
                "guidance": "invalidated",
                "live_price": 13.1,
                "entry": 15.1,
                "stop_loss": 14.8,
                "price_target": 16.8,
                "delta_vs_entry_pct": -13.24,
                "delta_vs_stop_pct": -11.49,
                "delta_vs_target_pct": -22.02,
            },
            "historical_rating_note": "historical",
        },
    )

    worker = main._worker
    assert worker is not None
    job_id = worker.store.create("MNSO", "2026-05-25", {})
    worker.store.set_result(
        job_id,
        {
            "ticker": "MNSO",
            "date": "2026-05-25",
            "rating": "Buy",
            "confidence": 0.92,
            "reports": {
                "trader_plan": "**Action**: Buy\n**Entry Price**: 15.1\n**Stop Loss**: 14.8",
                "portfolio_decision": "**Price Target**: 16.8",
            },
            "completed_at": "2026-05-25T12:00:00Z",
        },
    )

    live = api_client.get(f"/api/jobs/{job_id}/live-context")
    assert live.status_code == 200
    body = live.json()
    assert body["comparison"]["status"] == "below_stop"
    assert body["quote"]["price"] == 13.1


@pytest.mark.unit
def test_live_context_409_when_not_completed(api_client: TestClient):
    from api import main

    worker = main._worker
    assert worker is not None
    job_id = worker.store.create("MNSO", "2026-05-25", {})

    live = api_client.get(f"/api/jobs/{job_id}/live-context")
    assert live.status_code == 409

    missing = api_client.get("/api/jobs/doesnot1/live-context")
    assert missing.status_code == 404
