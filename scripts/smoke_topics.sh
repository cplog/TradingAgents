#!/usr/bin/env bash
# Smoke test for Topics API (requires running API or uses TestClient inline).
set -euo pipefail
cd "$(dirname "$0")/.."

export OPENAI_API_KEY="${OPENAI_API_KEY:-sk-test-placeholder}"
export TAVILY_API_KEY="${TAVILY_API_KEY:-tvly-test}"

echo "== Topics unit tests =="
pytest -m unit tests/test_topics_store.py tests/test_tavily.py tests/test_topics_extract.py tests/test_api_topics.py tests/test_topics_scheduler.py -q

echo "== Topics smoke (in-process) =="
python - <<'PY'
from fastapi.testclient import TestClient
import os
from pathlib import Path

tmp = Path("/tmp/ta_topics_smoke")
tmp.mkdir(exist_ok=True)
os.environ["TRADINGAGENTS_API_STATE_FILE"] = str(tmp / "state.json")
os.environ["OPENAI_API_KEY"] = "sk-test"
os.environ["TAVILY_API_KEY"] = "tvly-test"
for cf_var in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_KV_NAMESPACE_ID", "CLOUDFLARE_API_TOKEN"):
    os.environ.pop(cf_var, None)

from api.state_store import reset_state_store_for_tests
from api.topics_store import reset_topics_store_for_tests

reset_state_store_for_tests()
reset_topics_store_for_tests()

# Patch external calls before app import side effects
import api.topics as topics_mod
topics_mod.tavily_search = lambda q, **kw: [{"title": "Smoke", "url": "https://example.com", "snippet": "NVDA"}]
from api.topics_models import ExtractionResult, TickerCandidate, TickerMarket
topics_mod.extract_from_articles = lambda a, q, c: ExtractionResult(
    theme_summary="Smoke OK",
    candidates=[TickerCandidate(ticker="NVDA", confidence=0.8, market=TickerMarket.us)],
)

from api.main import app

with TestClient(app) as client:
    r = client.get("/api/topics")
    assert r.status_code == 200, r.text
    assert len(r.json()["topics"]) >= 10
    s = client.post("/api/topics/search", json={"query": "smoke test theme"})
    assert s.status_code == 200, s.text
    tid = s.json()["topic"]["id"]
    d = client.get(f"/api/topics/{tid}")
    assert d.status_code == 200
    print("topics smoke OK:", tid)
PY

echo "Done."
