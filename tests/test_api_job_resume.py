"""API job resume from LangGraph checkpoints."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from api.jobs import JobStore
from api.kronos.config import KronosConfig
from api.state_store import reset_state_store_for_tests


class _FailOnceGraph:
    calls = 0

    def __init__(self, **kwargs):
        pass

    def propagate(self, ticker, date, **kwargs):
        _FailOnceGraph.calls += 1
        if _FailOnceGraph.calls == 1:
            raise RuntimeError("simulated pipeline failure")
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
    monkeypatch.setenv("TRADINGAGENTS_CACHE_DIR", str(tmp_path / "cache"))
    for cf_var in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_KV_NAMESPACE_ID", "CLOUDFLARE_API_TOKEN"):
        monkeypatch.delenv(cf_var, raising=False)
    reset_state_store_for_tests()
    _FailOnceGraph.calls = 0
    monkeypatch.setattr("api.jobs.TradingAgentsGraph", _FailOnceGraph)
    monkeypatch.setattr(
        "api.jobs.KronosConfig.from_env",
        lambda: KronosConfig(enabled=False),
    )

    from api.main import app

    with TestClient(app) as client:
        yield client


def _wait_for_status(client: TestClient, job_id: str, *, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    body: dict = {}
    while time.time() < deadline:
        body = client.get(f"/jobs/{job_id}").json()
        if body.get("status") in ("completed", "failed"):
            return body
        time.sleep(0.05)
    return body


@pytest.mark.unit
def test_service_config_enables_checkpoints_by_default(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_CHECKPOINT_ENABLED", raising=False)
    from api.config import build_service_config

    cfg = build_service_config()
    assert cfg["checkpoint_enabled"] is True


@pytest.mark.unit
def test_resume_endpoint_requires_failed_job(api_client: TestClient, monkeypatch):
    class _SuccessGraph:
        def __init__(self, **kwargs):
            pass

        def propagate(self, ticker, date, **kwargs):
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

    monkeypatch.setattr("api.jobs.TradingAgentsGraph", _SuccessGraph)

    r = api_client.post(
        "/analyze",
        json={"ticker": "AAPL", "config_overrides": {"dimensions_enabled": False}},
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    body = _wait_for_status(api_client, job_id)
    assert body["status"] == "completed"

    bad = api_client.post(f"/jobs/{job_id}/resume")
    assert bad.status_code == 409


@pytest.mark.unit
def test_resume_requeues_failed_job_with_checkpoint(api_client: TestClient, monkeypatch):
    monkeypatch.setattr("api.jobs.checkpoint_step", lambda *args, **kwargs: 7)
    monkeypatch.setattr("api.jobs.thread_id", lambda ticker, date: "checkpoint-thread-7")

    r = api_client.post(
        "/analyze",
        json={"ticker": "MSFT", "config_overrides": {"dimensions_enabled": False}},
    )
    job_id = r.json()["job_id"]
    body = _wait_for_status(api_client, job_id)

    assert body["status"] == "failed"
    assert body["resumable"] is True
    assert body["last_graph_step"] == 7
    assert _FailOnceGraph.calls == 1

    resume = api_client.post(f"/jobs/{job_id}/resume")
    assert resume.status_code == 200
    payload = resume.json()
    assert payload["job_id"] == job_id
    assert payload["status"] == "queued"
    assert payload["last_graph_step"] == 7

    body = _wait_for_status(api_client, job_id)
    assert body["status"] == "completed"
    assert _FailOnceGraph.calls == 2


@pytest.mark.unit
def test_job_store_prepare_resume(tmp_path, monkeypatch):
    monkeypatch.setattr("api.jobs.checkpoint_step", lambda *args, **kwargs: 5)
    monkeypatch.setattr("api.jobs.thread_id", lambda ticker, date: "tid-5")

    store = JobStore(ttl_hours=1)
    cfg = {"checkpoint_enabled": True, "data_cache_dir": str(tmp_path)}
    jid = store.create("AAPL", "2026-01-15", cfg, analysts=["market"])
    store.set_error(jid, "RuntimeError: boom")

    refreshed = store.get(jid)
    assert refreshed.resumable is True
    assert refreshed.last_graph_step == 5

    assert store.prepare_resume(jid) is not None
    again = store.get(jid)
    assert again.status == "queued"
    assert again.error is None
    assert any("Resuming from LangGraph checkpoint" in e["message"] for e in again.progress_events)
