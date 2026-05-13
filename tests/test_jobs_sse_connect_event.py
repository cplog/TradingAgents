import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.jobs import Worker
import api.main as main_module


@pytest.fixture
def client_with_job(monkeypatch):
    worker = Worker(max_concurrency=1, ttl_hours=1)
    monkeypatch.setattr(main_module, "_worker", worker)
    jid = worker.store.create("AAPL", "2026-05-13", {})
    return TestClient(app), jid


def test_sse_first_event_is_connected_with_retry(client_with_job):
    client, jid = client_with_job
    with client.stream("GET", f"/jobs/{jid}/events") as r:
        body = b""
        for chunk in r.iter_bytes():
            body += chunk
            if b"\n\n" in body:
                break
    text = body.decode("utf-8")
    assert "retry: 5000" in text
    first_data_line = next(
        (ln for ln in text.split("\n") if ln.startswith("data:")), ""
    )
    payload = json.loads(first_data_line.removeprefix("data: ").strip())
    assert payload["type"] == "connected"
    assert "cursor" in payload
    assert "status" in payload
