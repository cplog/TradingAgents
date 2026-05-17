import asyncio
from unittest.mock import MagicMock, patch

import pytest

from api.jobs import Worker
from api.dimensions.schemas import (
    StockDimensions, FactSnapshot, PillarScores, MarketPillar, SentimentPillar,
    NewsPillar, FundamentalsPillar, PillarScore, FactorScores, FactorScore,
    DimensionsCommentary,
)


def _ps(s=3):
    return PillarScore(score=s, rationale="x")


def _fake_dimensions():
    return StockDimensions(
        ticker="AAPL", as_of_date="2026-05-13",
        facts=FactSnapshot(as_of_date="2026-05-13", currency="USD",
                          sector="Technology", industry="Consumer Electronics"),
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


def _fake_commentary():
    return DimensionsCommentary(alignment="aligned", supporting_dimensions=["value"],
                               conflicting_dimensions=[], risk_flags=[], summary="ok")


@pytest.mark.asyncio
async def test_dimensions_phase_emits_six_progress_events(monkeypatch):
    worker = Worker(max_concurrency=1, ttl_hours=24)

    monkeypatch.setattr(
        "api.jobs.Worker._propagate_sync",
        lambda self, *a, **k: ({"market_report": "x", "sentiment_report": "y",
                                "news_report": "z", "fundamentals_report": "w",
                                "final_trade_decision": "Buy.",
                                "company_of_interest": "AAPL",
                                "trade_date": "2026-05-13",
                                "investment_debate_state": {},
                                "risk_debate_state": {}}, "Buy"),
    )
    monkeypatch.setattr("api.jobs.build_dimensions",
                       lambda **k: _fake_dimensions())
    monkeypatch.setattr("api.jobs.build_commentary",
                       lambda **k: _fake_commentary())

    jid = await worker.submit("AAPL", "2026-05-13", {"dimensions_enabled": True})
    for _ in range(100):
        rec = worker.store.get(jid)
        if rec and rec.status in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    rec = worker.store.get(jid)
    assert rec.status == "completed"
    dim_events = [e for e in rec.progress_events if e.get("stage") == "dimensions"]
    assert len(dim_events) >= 6
    messages = " | ".join(e["message"] for e in dim_events)
    assert "quantitative inputs" in messages
    assert "scoring 16 pillars" in messages
    assert "commentary" in messages
