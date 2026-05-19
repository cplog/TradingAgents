import asyncio
import json
from unittest.mock import MagicMock

import pytest

from api.jobs import Worker
from api.dimensions.builder import DimensionsBuildError
from api.dimensions.schemas import (
    FactSnapshot,
    FactorScore,
    FactorScores,
    FundamentalsPillar,
    MarketPillar,
    NewsPillar,
    PillarScore,
    PillarScores,
    SentimentPillar,
    StockDimensions,
)


def _ps(s: int = 3) -> PillarScore:
    return PillarScore(score=s, rationale="x")


def _graph_dims() -> dict:
    dims = StockDimensions(
        ticker="AAPL",
        as_of_date="2026-05-13",
        facts=FactSnapshot(as_of_date="2026-05-13", currency="USD"),
        pillar_scores=PillarScores(
            market=MarketPillar(
                trend=_ps(), momentum=_ps(), volatility_risk=_ps(), setup_quality=_ps()
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
    return dims.model_dump(mode="python")


@pytest.mark.asyncio
async def test_dimensions_failure_does_not_fail_job(monkeypatch):
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

    def boom(**k):
        raise DimensionsBuildError("yfinance offline")
    monkeypatch.setattr("api.jobs.build_dimensions", boom)

    jid = await worker.submit("AAPL", "2026-05-13", {"dimensions_enabled": True})
    for _ in range(100):
        rec = worker.store.get(jid)
        if rec and rec.status in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    rec = worker.store.get(jid)
    assert rec.status == "completed"
    assert rec.result is not None
    assert rec.result.get("dimensions") is None
    assert rec.result.get("dimensions_error") is not None
    assert "yfinance offline" in rec.result["dimensions_error"]
    skipped = [e for e in rec.progress_events if e.get("stage") == "dimensions_skipped"]
    assert len(skipped) == 1


@pytest.mark.asyncio
async def test_commentary_failure_preserves_reused_dimensions_snapshot(monkeypatch):
    worker = Worker(max_concurrency=1, ttl_hours=24)
    graph_dims = _graph_dims()

    monkeypatch.setattr(
        "api.jobs.Worker._propagate_sync",
        lambda self, *a, **k: (
            {
                "market_report": "x",
                "sentiment_report": "y",
                "news_report": "z",
                "fundamentals_report": "w",
                "final_trade_decision": "Buy.",
                "company_of_interest": "AAPL",
                "trade_date": "2026-05-13",
                "investment_debate_state": {},
                "risk_debate_state": {},
                "dimensions_snapshot_json": json.dumps(graph_dims, ensure_ascii=False),
            },
            "Buy",
        ),
    )

    def boom(**k):
        raise DimensionsBuildError("Commentary failed: structured output broken")

    monkeypatch.setattr("api.jobs.build_commentary", boom)
    monkeypatch.setattr(
        "tradingagents.llm_clients.create_llm_client",
        lambda **k: MagicMock(get_llm=lambda: MagicMock()),
    )

    jid = await worker.submit(
        "AAPL",
        "2026-05-13",
        {"dimensions_enabled": True, "dimensions_in_graph": True},
    )
    for _ in range(100):
        rec = worker.store.get(jid)
        if rec and rec.status in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    rec = worker.store.get(jid)
    assert rec.status == "completed"
    assert rec.result is not None
    assert rec.result.get("dimensions") is not None
    assert rec.result["dimensions"]["ticker"] == "AAPL"
    assert rec.result.get("dimensions_commentary") is None
    assert "Commentary failed" in rec.result.get("dimensions_error", "")
    skipped = [
        e for e in rec.progress_events if e.get("stage") == "dimensions_commentary_skipped"
    ]
    assert len(skipped) == 1
