"""API tests for /api/hpm/score endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.state_store import reset_state_store_for_tests
from api.topics_store import reset_topics_store_for_tests
from api.topics import reset_topics_engine_for_tests


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("TRADINGAGENTS_API_STATE_FILE", str(tmp_path / "api_state.json"))
    for cf_var in (
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_KV_NAMESPACE_ID",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_D1_DATABASE_ID",
    ):
        monkeypatch.delenv(cf_var, raising=False)
    monkeypatch.setattr("api.history.d1_history_enabled", lambda: False)
    reset_state_store_for_tests()
    reset_topics_store_for_tests()
    reset_topics_engine_for_tests()

    from api.main import app

    with TestClient(app) as client:
        yield client


@pytest.mark.unit
def test_hpm_score_default_index(api_client: TestClient):
    r = api_client.get("/api/hpm/score")
    assert r.status_code == 200
    body = r.json()
    assert body["index"] == "SPY"
    assert "composite_score" in body
    assert 0.0 <= body["composite_score"] <= 5.0
    assert "trading_posture" in body
    assert "regime_confidence" in body
    assert "regime_reason_codes" in body
    assert "dominant_transmission_chain" in body
    assert "timestamp" in body
    assert "signals" in body
    assert len(body["signals"]) == 4


@pytest.mark.unit
def test_hpm_score_custom_index(api_client: TestClient):
    r = api_client.get("/api/hpm/score?index=QQQ")
    assert r.status_code == 200
    body = r.json()
    assert body["index"] == "QQQ"
    assert body["composite_score"] != pytest.approx(
        api_client.get("/api/hpm/score?index=SPY").json()["composite_score"],
        abs=1e-6,
    )


@pytest.mark.unit
def test_hpm_score_reproducible(api_client: TestClient):
    r1 = api_client.get("/api/hpm/score?index=IWM")
    r2 = api_client.get("/api/hpm/score?index=IWM")
    assert r1.json()["composite_score"] == r2.json()["composite_score"]
    assert r1.json()["trading_posture"] == r2.json()["trading_posture"]
    assert r1.json()["regime_confidence"] == r2.json()["regime_confidence"]


@pytest.mark.unit
def test_hpm_score_signals_structure(api_client: TestClient):
    r = api_client.get("/api/hpm/score")
    body = r.json()
    for name, sig in body["signals"].items():
        assert "score" in sig
        assert "direction" in sig
        assert "detail" in sig
        assert 0.0 <= sig["score"] <= 1.0
        assert sig["direction"] in ("up", "down", "flat")
