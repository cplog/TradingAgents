"""Topics API route tests."""

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

    def fake_search(query, **kwargs):
        return [
            {
                "title": "Chip stocks rally",
                "url": "https://example.com/chips",
                "snippet": "NVDA AMD lead",
                "source": "tavily",
            }
        ]

    monkeypatch.setattr("api.topics.tavily_search", fake_search)

    from api.topics_models import ExtractionResult, TickerCandidate, TickerMarket

    def fake_extract(articles, query, service_config):
        return ExtractionResult(
            theme_summary="Chips are trending.",
            candidates=[TickerCandidate(ticker="NVDA", confidence=0.88, market=TickerMarket.us)],
        )

    monkeypatch.setattr("api.topics.extract_from_articles", fake_extract)

    async def _seed_only_start(self):
        self.store.ensure_seed_topics()

    monkeypatch.setattr("api.topics.TopicsEngine.start", _seed_only_start)

    from api.main import app

    with TestClient(app) as client:
        yield client


@pytest.mark.unit
def test_topics_list_seeds(api_client: TestClient):
    r = api_client.get("/api/topics")
    assert r.status_code == 200
    body = r.json()
    assert "topics" in body
    assert len(body["topics"]) >= 10


@pytest.mark.unit
def test_topics_search(api_client: TestClient):
    r = api_client.post("/api/topics/search", json={"query": "quantum computing stocks"})
    assert r.status_code == 200
    body = r.json()
    assert body["topic"]["query"] == "quantum computing stocks"
    assert body["latest_run"]["status"] == "completed"
    assert body["latest_run"]["candidates"][0]["ticker"] == "NVDA"


@pytest.mark.unit
def test_topics_get_and_runs(api_client: TestClient):
    created = api_client.post("/api/topics/search", json={"query": "robotics automation"})
    topic_id = created.json()["topic"]["id"]
    r = api_client.get(f"/api/topics/{topic_id}")
    assert r.status_code == 200
    runs = api_client.get(f"/api/topics/{topic_id}/runs")
    assert runs.status_code == 200
    assert len(runs.json()["runs"]) >= 1


@pytest.mark.unit
def test_topics_pin_patch(api_client: TestClient):
    created = api_client.post("/api/topics/search", json={"query": "water utilities"})
    topic_id = created.json()["topic"]["id"]
    pin = api_client.post(f"/api/topics/{topic_id}/pin")
    assert pin.status_code == 200
    assert pin.json()["topic"]["pinned"] is True
    patch = api_client.patch(f"/api/topics/{topic_id}", json={"label": "Water"})
    assert patch.status_code == 200
    assert patch.json()["topic"]["label"] == "Water"


@pytest.mark.unit
def test_topics_refresh_cooldown(api_client: TestClient):
    from api.state_store import get_state_store
    from api.topics_store import get_topics_store, _budget_key
    from api.topics_models import TopicSource
    from api.topics import _today_utc

    store = get_topics_store(get_state_store())
    day = _today_utc()
    get_state_store().put_json(_budget_key(day), {"count": 0, "day": day})

    topic = store.upsert_by_query("cooldown-only-theme", source=TopicSource.user)
    topic.last_refresh_at = None
    store.save_topic(topic)

    r1 = api_client.post(f"/api/topics/{topic.id}/refresh")
    assert r1.status_code == 200
    r2 = api_client.post(f"/api/topics/{topic.id}/refresh")
    assert r2.status_code == 429


@pytest.mark.unit
def test_topics_delete_seed_forbidden(api_client: TestClient):
    listed = api_client.get("/api/topics").json()["topics"]
    seed_id = listed[0]["id"]
    r = api_client.delete(f"/api/topics/{seed_id}")
    assert r.status_code == 403


@pytest.mark.unit
def test_topics_delete_user(api_client: TestClient):
    created = api_client.post("/api/topics/search", json={"query": "temp user theme xyz"})
    topic_id = created.json()["topic"]["id"]
    r = api_client.delete(f"/api/topics/{topic_id}")
    assert r.status_code == 200
    assert api_client.get(f"/api/topics/{topic_id}").status_code == 404


@pytest.mark.unit
def test_topics_alias_routes(api_client: TestClient):
    r = api_client.get("/topics")
    assert r.status_code == 200
