"""History API — persist on complete, list, detail, compare."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from api.state_store import reset_state_store_for_tests


class _FakeGraph:
    """Minimal state so api.reports.build_result succeeds."""

    def __init__(self, **kwargs):
        pass

    def propagate(self, ticker, date):
        pm = "## PM decision\n\n**Hold** — test."
        return (
            {
                "market_report": "## Market\nOK",
                "news_report": "## News\nOK",
                "investment_debate_state": {
                    "judge_decision": "## RM\nPlan",
                    "bull_history": "",
                    "bear_history": "",
                },
                "trader_investment_plan": "### Trader\nStop loss: ...",
                "risk_debate_state": {
                    "judge_decision": pm,
                    "aggressive_history": "",
                    "conservative_history": "",
                    "neutral_history": "",
                },
                "final_trade_decision": pm,
            },
            "Hold",
        )


def _wait_job(client: TestClient, job_id: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/jobs/{job_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        st = body.get("status")
        if st == "completed":
            return
        if st == "failed":
            raise AssertionError(f"job failed: {body}")
        time.sleep(0.05)
    raise AssertionError("timeout waiting for job")


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
def test_history_bad_date_filters(api_client: TestClient):
    r = api_client.get("/api/history/runs?date_from=not-valid")
    assert r.status_code == 400


@pytest.mark.unit
def test_history_compare_not_found(api_client: TestClient):
    r = api_client.post(
        "/api/history/compare",
        json={"run_id_a": "xxxxxxxx", "run_id_b": "yyyyyyyy"},
    )
    assert r.status_code == 404


@pytest.mark.unit
def test_history_persist_list_detail_and_compare(api_client: TestClient):
    r1 = api_client.post("/analyze", json={"ticker": "AAPL"})
    assert r1.status_code == 200
    jid1 = r1.json()["job_id"]

    r2 = api_client.post("/analyze", json={"ticker": "MSFT"})
    assert r2.status_code == 200
    jid2 = r2.json()["job_id"]

    _wait_job(api_client, jid1)
    _wait_job(api_client, jid2)

    listed = api_client.get("/api/history/runs").json()
    assert isinstance(listed, list)
    assert len(listed) >= 2
    ids_found = {row["run_id"] for row in listed}
    assert jid1 in ids_found and jid2 in ids_found

    by_ticker = api_client.get("/api/history/runs?ticker=AAPL").json()
    assert all(str(row.get("ticker")) == "AAPL" for row in by_ticker)

    cmp = api_client.post(
        "/api/history/compare",
        json={"run_id_a": jid1, "run_id_b": jid2},
    )
    assert cmp.status_code == 200
    cj = cmp.json()
    assert cj["a"]["ticker"] == "AAPL"
    assert cj["b"]["ticker"] == "MSFT"
    assert isinstance(cj["a"].get("excerpt_portfolio_decision"), str)
    assert "reports" in cj["a"] and "portfolio_decision" in cj["a"]["reports"]


@pytest.mark.unit
def test_history_delete_run(api_client: TestClient):
    r = api_client.post("/analyze", json={"ticker": "AAPL"})
    assert r.status_code == 200
    run_id = r.json()["job_id"]
    _wait_job(api_client, run_id)

    before = api_client.get("/api/history/runs").json()
    assert any(row.get("run_id") == run_id for row in before)

    deleted = api_client.delete(f"/api/history/runs/{run_id}")
    assert deleted.status_code == 200
    assert deleted.json().get("deleted") is True

    detail = api_client.get(f"/api/history/runs/{run_id}")
    assert detail.status_code == 404

    after = api_client.get("/api/history/runs").json()
    assert all(row.get("run_id") != run_id for row in after)


@pytest.mark.unit
def test_history_bulk_delete_runs(api_client: TestClient):
    ids = []
    for ticker in ("AAPL", "MSFT", "NVDA"):
        r = api_client.post("/analyze", json={"ticker": ticker})
        assert r.status_code == 200
        jid = r.json()["job_id"]
        _wait_job(api_client, jid)
        ids.append(jid)

    bulk = api_client.post(
        "/api/history/runs/bulk-delete",
        json={"run_ids": [ids[0], ids[1]]},
    )
    assert bulk.status_code == 200
    body = bulk.json()
    assert body["deleted_count"] == 2
    assert set(body["deleted_run_ids"]) == {ids[0], ids[1]}

    listed = api_client.get("/api/history/runs").json()
    remaining = {row["run_id"] for row in listed}
    assert ids[2] in remaining
    assert ids[0] not in remaining
    assert ids[1] not in remaining


@pytest.mark.unit
def test_history_delete_all_requires_confirm(api_client: TestClient):
    r = api_client.post(
        "/api/history/runs/delete-all",
        json={"confirm": False},
    )
    assert r.status_code == 400


@pytest.mark.unit
def test_history_delete_all_matching_filters(api_client: TestClient):
    for ticker in ("AAPL", "MSFT"):
        r = api_client.post("/analyze", json={"ticker": ticker})
        jid = r.json()["job_id"]
        _wait_job(api_client, jid)

    cleared = api_client.post(
        "/api/history/runs/delete-all",
        json={"confirm": True, "ticker": "AAPL"},
    )
    assert cleared.status_code == 200
    assert cleared.json()["deleted_count"] >= 1

    listed = api_client.get("/api/history/runs").json()
    tickers = {row.get("ticker") for row in listed}
    assert "AAPL" not in tickers
    assert "MSFT" in tickers

    wipe = api_client.post(
        "/api/history/runs/delete-all",
        json={"confirm": True},
    )
    assert wipe.status_code == 200
    assert api_client.get("/api/history/runs").json() == []
