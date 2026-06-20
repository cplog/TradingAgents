"""Monitor API endpoints (watchlist, status, tick)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from api.state_store import reset_state_store_for_tests
from api.notifications import get_manager, reset_manager_for_tests


class _FakeGraph:
    """Minimal graph stub for analyze/scan tests."""

    def __init__(self, **kwargs):
        self.selected_analysts = kwargs.get("selected_analysts")

    def propagate(self, ticker, date):
        return ({"market_report": "ok"}, "Hold")


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder")
    monkeypatch.setenv("TRADINGAGENTS_API_STATE_FILE", str(tmp_path / "api_state.json"))
    for cf_var in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_KV_NAMESPACE_ID", "CLOUDFLARE_API_TOKEN"):
        monkeypatch.delenv(cf_var, raising=False)
    reset_state_store_for_tests()
    monkeypatch.setattr("api.jobs.TradingAgentsGraph", _FakeGraph)

    from api.main import app

    with TestClient(app) as client:
        yield client


@pytest.mark.unit
def test_monitor_status(api_client: TestClient):
    r = api_client.get("/api/monitor/status")
    assert r.status_code == 200
    body = r.json()
    assert "watchlist" in body
    assert "session" in body


@pytest.mark.unit
def test_monitor_watchlist_crud(api_client: TestClient):
    r = api_client.put("/api/monitor/watchlist", json={"tickers": ["AAPL", "MSFT"]})
    assert r.status_code == 200
    assert set(r.json()["tickers"]) == {"AAPL", "MSFT"}

    r2 = api_client.get("/api/monitor/watchlist")
    assert r2.status_code == 200
    assert set(r2.json()["tickers"]) == {"AAPL", "MSFT"}

    r3 = api_client.post("/api/monitor/watchlist", json={"ticker": "nvda"})
    assert r3.status_code == 200
    assert "NVDA" in r3.json()["tickers"]

    r4 = api_client.delete("/api/monitor/watchlist/AAPL")
    assert r4.status_code == 200
    assert "AAPL" not in r4.json()["tickers"]


@pytest.mark.unit
def test_monitor_tick_empty_watchlist(api_client: TestClient, monkeypatch):
    monkeypatch.setattr(
        "api.monitor.engine.scan_us_panic_candidates",
        lambda **kwargs: [],
    )
    api_client.put("/api/monitor/watchlist", json={"tickers": []})
    r = api_client.post("/api/monitor/tick")
    assert r.status_code == 200
    body = r.json()
    assert body.get("message") == "empty watchlist" or "triggered" in body


@pytest.mark.unit
def test_monitor_tick_sends_notification(api_client: TestClient, monkeypatch):
    reset_manager_for_tests()
    monkeypatch.setattr(
        "api.monitor.engine.scan_us_panic_candidates",
        lambda **kwargs: [{"ticker": "AAPL", "change_pct": -12.5}],
    )

    class _FakeSignal:
        score = 85
        change_pct = -12.5

        def to_dict(self):
            return {"score": self.score, "change_pct": self.change_pct}

    monkeypatch.setattr(
        "api.monitor.engine.compute_overnight_signal",
        lambda *args, **kwargs: _FakeSignal(),
    )
    monkeypatch.setattr(
        "tradingagents.dataflows.config.set_config",
        lambda *args, **kwargs: None,
    )
    sent = []

    async def fake_send(title, body, tags=None, force=False):
        sent.append({"title": title, "body": body, "tags": tags})
        return {"sent": True}

    monkeypatch.setattr(get_manager(), "send", fake_send)
    api_client.put("/api/monitor/watchlist", json={"tickers": ["AAPL"]})
    r = api_client.post("/api/monitor/tick")
    assert r.status_code == 200
    assert any("AAPL" in s["title"] for s in sent)


@pytest.mark.unit
def test_analyze_scan_mode(api_client: TestClient):
    r = api_client.post(
        "/analyze",
        json={"ticker": "AAPL", "mode": "scan"},
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    for _ in range(40):
        j = api_client.get(f"/jobs/{job_id}").json()
        if j.get("status") in ("completed", "failed"):
            break
        time.sleep(0.05)

    job = api_client.get(f"/jobs/{job_id}").json()
    assert job.get("trigger") == "scan"
