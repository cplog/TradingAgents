"""API UX endpoints (health, batch shape, SSE stub, admin guards)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.models import DEFAULT_ANALYST_ORDER
from api.state_store import reset_state_store_for_tests


class _FakeGraph:
    """Returns minimal state so api.reports.build_result succeeds."""

    def __init__(self, **kwargs):
        pass

    def propagate(self, ticker, date):
        return (
            {
                "market_report": "## Market\nOK",
                "investment_debate_state": {
                    "judge_decision": "## RM\nPlan",
                    "bull_history": "",
                    "bear_history": "",
                },
                "risk_debate_state": {
                    "judge_decision": "## PM\n**Buy** — test",
                    "aggressive_history": "",
                    "conservative_history": "",
                    "neutral_history": "",
                },
            },
            "Buy",
        )


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder")
    monkeypatch.setenv("TRADINGAGENTS_API_STATE_FILE", str(tmp_path / "api_state.json"))
    for cf_var in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_KV_NAMESPACE_ID", "CLOUDFLARE_API_TOKEN"):
        monkeypatch.delenv(cf_var, raising=False)
    reset_state_store_for_tests()
    monkeypatch.setattr("api.jobs.TradingAgentsGraph", _FakeGraph)

    # Import app after env so lifespan validates keys
    from api.main import app

    with TestClient(app) as client:
        yield client


@pytest.mark.unit
def test_plain_health(api_client: TestClient):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.text == "ok"


@pytest.mark.unit
def test_api_health(api_client: TestClient):
    r = api_client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "llm_provider" in body
    assert body["api_key_configured"] is True
    assert body["supported_analyst_ids"] == list(DEFAULT_ANALYST_ORDER)


@pytest.mark.unit
def test_batch_and_job_poll(api_client: TestClient):
    r = api_client.post("/batches", json={"tickers": ["AAPL", "MSFT"]})
    assert r.status_code == 200
    batch_id = r.json()["batch_id"]
    r2 = api_client.get(f"/batches/{batch_id}")
    assert r2.status_code == 200
    jobs = r2.json()["jobs"]
    assert len(jobs) == 2
    assert all("job_id" in j for j in jobs)


@pytest.mark.unit
def test_sse_not_found(api_client: TestClient):
    with api_client.stream("GET", "/jobs/nope000/events") as resp:
        assert resp.status_code == 200
        text = "".join(resp.iter_text())
    assert "not found" in text.lower() or "error" in text.lower()


@pytest.mark.unit
def test_admin_disabled_without_key(api_client: TestClient, monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_ADMIN_KEY", raising=False)
    from api import main as main_mod

    main_mod._load_persisted_into_process()
    r = api_client.post("/admin/cache/clear", json={})
    assert r.status_code == 503


@pytest.mark.unit
def test_admin_jobs_clear(api_client: TestClient, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_ADMIN_KEY", "admin-test-key")
    from api import main as main_mod

    main_mod._worker.store.create("AAPL", "2026-05-14", {})
    main_mod._worker.store.create("MSFT", "2026-05-14", {})

    r = api_client.post(
        "/admin/jobs/clear",
        json={"mode": "all"},
        headers={"X-Admin-Key": "admin-test-key"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["cleared"] is True
    assert body["mode"] == "all"
    assert body["jobs_removed"] >= 2

    r2 = api_client.get("/jobs")
    assert r2.status_code == 200
    assert r2.json() == []


@pytest.mark.unit
def test_news_endpoint_structure(api_client: TestClient, monkeypatch):
    def fake_fetch(ticker, **kwargs):
        from datetime import datetime

        from api.models import NewsFeedResponse, NewsItem

        return NewsFeedResponse(
            ticker=ticker,
            items=[
                NewsItem(
                    title="Test headline rally",
                    summary="Growth beat",
                    publisher="TestPub",
                    link="https://example.com",
                    pub_date="2026-01-01T00:00:00Z",
                    ticker=ticker,
                    sentiment="bullish",
                    sentiment_score=0.5,
                    sector_tags=[],
                    source="yfinance",
                )
            ],
            fetched_at=datetime.utcnow(),
        )

    monkeypatch.setattr("api.main.fetch_news_feed", fake_fetch)
    r = api_client.get("/news/AAPL")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert len(body["items"]) == 1
    assert body["items"][0]["sentiment"] == "bullish"


@pytest.mark.unit
def test_analyze_rejects_missing_ollama_remote_auth(api_client: TestClient, monkeypatch):
    monkeypatch.delenv("OLLAMA_CF_TOKEN", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_CF_CLIENT_ID", raising=False)
    monkeypatch.delenv("OLLAMA_CF_CLIENT_SECRET", raising=False)
    r = api_client.post(
        "/analyze",
        json={"ticker": "AAPL", "config_overrides": {"llm_provider": "ollama-remote"}},
    )
    assert r.status_code == 400
    assert "ollama-remote" in r.text.lower()
