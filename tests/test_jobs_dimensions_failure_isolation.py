import asyncio

import pytest

from api.jobs import Worker
from api.dimensions.builder import DimensionsBuildError


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
