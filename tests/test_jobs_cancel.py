import asyncio

import pytest

from api.jobs import Worker


@pytest.mark.asyncio
async def test_request_cancellation_flag_settable():
    worker = Worker(max_concurrency=1, ttl_hours=24)
    jid = worker.store.create("AAPL", "2026-05-13", {})
    assert worker.store.request_cancellation(jid) is True
    rec = worker.store.get(jid)
    assert rec.cancellation_requested is True


@pytest.mark.asyncio
async def test_cancel_all_active_marks_queued_cancelled():
    worker = Worker(max_concurrency=1, ttl_hours=24)
    q1 = worker.store.create("AAPL", "2026-05-13", {})
    q2 = worker.store.create("MSFT", "2026-05-13", {})
    worker.store.update_status(q1, "running")

    stopped = worker.store.cancel_all_active()
    assert set(stopped) == {q1, q2}
    assert worker.store.get(q1).cancellation_requested is True
    assert worker.store.get(q2).status == "cancelled"


@pytest.mark.asyncio
async def test_cancellation_before_dimensions_skips_them(monkeypatch):
    worker = Worker(max_concurrency=1, ttl_hours=24)

    def propagate(self, *a, **k):
        # Mark cancellation just before returning
        for jid in self.store.list_ids():
            self.store.request_cancellation(jid)
        return ({"market_report": "x", "sentiment_report": "y", "news_report": "z",
                 "fundamentals_report": "w", "final_trade_decision": "Buy.",
                 "company_of_interest": "AAPL", "trade_date": "2026-05-13",
                 "investment_debate_state": {}, "risk_debate_state": {}}, "Buy")

    monkeypatch.setattr("api.jobs.Worker._propagate_sync", propagate)

    called = {"dim": 0, "comm": 0}
    monkeypatch.setattr("api.jobs.build_dimensions",
                       lambda **k: (called.__setitem__("dim", called["dim"] + 1), None)[1])
    monkeypatch.setattr("api.jobs.build_commentary",
                       lambda **k: (called.__setitem__("comm", called["comm"] + 1), None)[1])

    jid = await worker.submit("AAPL", "2026-05-13", {"dimensions_enabled": True})
    for _ in range(100):
        rec = worker.store.get(jid)
        if rec and rec.status in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.05)

    rec = worker.store.get(jid)
    assert rec.status == "completed"
    assert called["dim"] == 0
    assert called["comm"] == 0
