import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.jobs import Worker
import api.main as main_module
from api.dimensions.schemas import (
    StockDimensions, FactSnapshot, PillarScores, MarketPillar, SentimentPillar,
    NewsPillar, FundamentalsPillar, PillarScore, FactorScores, FactorScore,
)


def _ps(s=3):
    return PillarScore(score=s, rationale="x")


def _dim(ticker="AAPL"):
    return StockDimensions(
        ticker=ticker, as_of_date="2026-05-13",
        facts=FactSnapshot(as_of_date="2026-05-13", currency="USD"),
        pillar_scores=PillarScores(
            market=MarketPillar(trend=_ps(), momentum=_ps(), volatility_risk=_ps(),
                               setup_quality=_ps()),
            sentiment=SentimentPillar(retail_sentiment=_ps(), social_buzz=_ps(),
                                     consensus_quality=_ps(), narrative_strength=_ps()),
            news=NewsPillar(catalyst_strength=_ps(), macro_alignment=_ps(),
                           headline_quality=_ps(), surprise_risk=_ps()),
            fundamentals=FundamentalsPillar(valuation=_ps(), growth=_ps(),
                                           profitability=_ps(), balance_sheet_strength=_ps()),
        ),
        factor_scores=FactorScores(
            value=FactorScore(score=70.0), growth=FactorScore(score=60.0),
            quality=FactorScore(score=80.0), momentum=FactorScore(score=55.0),
            low_risk=FactorScore(score=40.0), sentiment=FactorScore(score=50.0),
        ),
        dimensions_version="1.0.0",
    )


@pytest.fixture
def client(monkeypatch):
    w = Worker(max_concurrency=1, ttl_hours=1)
    monkeypatch.setattr(main_module, "_worker", w)
    return TestClient(app), w


def test_get_jobs_dimensions_returns_404_unknown(client):
    c, _ = client
    r = c.get("/jobs/nope/dimensions")
    assert r.status_code == 404


def test_get_jobs_dimensions_returns_payload(client):
    c, w = client
    jid = w.store.create("AAPL", "2026-05-13", {})
    w.store.set_result(jid, {"dimensions": _dim().model_dump(),
                              "ticker": "AAPL", "date": "2026-05-13",
                              "rating": "Buy", "reports": {}})
    r = c.get(f"/jobs/{jid}/dimensions")
    assert r.status_code == 200
    assert r.json()["ticker"] == "AAPL"


def test_cancel_endpoint_sets_flag(client):
    c, w = client
    jid = w.store.create("AAPL", "2026-05-13", {})
    r = c.post(f"/jobs/{jid}/cancel")
    assert r.status_code == 200
    body = r.json()
    assert body["cancellation_requested"] is True
    rec = w.store.get(jid)
    assert rec.cancellation_requested is True


def test_cancel_endpoint_404_unknown(client):
    c, _ = client
    r = c.post("/jobs/nope/cancel")
    assert r.status_code == 404


def test_dimensions_by_ticker_facts_only(client, monkeypatch):
    c, _ = client
    from api.dimensions.schemas import StockDimensions
    fake = _dim("MSFT")
    fake = fake.model_copy(update={"source": "facts_only"})
    monkeypatch.setattr(
        "api.main.build_dimensions_facts_only",
        lambda **k: fake,
    )
    r = c.get("/dimensions/MSFT")
    assert r.status_code == 200
    assert r.json()["source"] == "facts_only"


def test_admin_peer_cache_refresh_requires_key(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("TRADINGAGENTS_ADMIN_KEY", "secret")
    r = c.post("/admin/dimensions/peer-cache/refresh",
               json={"sector": "Tech", "industry": "Soft"})
    assert r.status_code == 401
    r2 = c.post("/admin/dimensions/peer-cache/refresh",
                json={"sector": "Tech", "industry": "Soft"},
                headers={"X-Admin-Key": "secret"})
    # 200 even with no peers (returns 0 written)
    assert r2.status_code in (200, 503)
