"""Integration test: jobs.Worker._propagate_sync seeds kronos_report
via the monkey-patch on Propagator.create_initial_state, and merges
kronos_forecast / kronos_status into the returned final_state."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from api.jobs import Worker
from api.kronos.errors import InsufficientData, ModelLoadError
from api.kronos.schema import (
    KronosForecastPayload,
    KronosForecastRow,
)


def _ohlcv(n: int = 200) -> pd.DataFrame:
    ts = pd.date_range(end="2026-05-18", periods=n, freq="B")
    return pd.DataFrame({
        "timestamps": ts,
        "open": [100.0] * n, "high": [101.0] * n,
        "low": [99.0] * n, "close": [100.5] * n,
        "volume": [1_000_000.0] * n, "amount": [100_500_000.0] * n,
    })


def _payload() -> KronosForecastPayload:
    row = KronosForecastRow(
        date="2026-05-20", open=100.0, high=101.0, low=99.0,
        close=100.5, volume=1.0, amount=100.5,
    )
    return KronosForecastPayload(
        ticker="AAPL", trade_date="2026-05-19",
        model="NeoQuasar/Kronos-small", tokenizer="NeoQuasar/Kronos-Tokenizer-base",
        device="cpu", lookback=200, pred_len=1, sample_count=1,
        history_tail=[row], forecast=[row],
        generated_at="2026-05-19T12:00:00+00:00",
    )


def _make_graph_capture_seen_state():
    """Return (graph_mock, captured) where ``captured['seen_kronos_report']``
    is what the graph sees in its initial state during propagate()."""
    captured: dict = {}

    class FakePropagator:
        def __init__(self):
            self.calls = 0

        def create_initial_state(self, company_name, trade_date, past_context=""):
            self.calls += 1
            return {"kronos_report": "", "messages": [("human", company_name)]}

        def get_graph_args(self, callbacks=None):
            return {"stream_mode": "values", "config": {"recursion_limit": 100}}

    class FakeGraph:
        def __init__(self):
            self.propagator = FakePropagator()

        def propagate(self, ticker, date):
            state = self.propagator.create_initial_state(ticker, date)
            captured["seen_kronos_report"] = state["kronos_report"]
            return ({"market_report": "ok", "kronos_report": state["kronos_report"]},
                    "BUY")

    return FakeGraph(), captured


def test_propagate_sync_seeds_kronos_report_with_real_forecast():
    graph, captured = _make_graph_capture_seen_state()
    with patch("api.jobs.TradingAgentsGraph", return_value=graph), \
         patch("api.jobs.fetch_ohlcv", return_value=_ohlcv()), \
         patch("api.jobs.KronosService") as svc_cls:
        svc_cls.get.return_value.forecast.return_value = _payload()
        worker = Worker(max_concurrency=1)
        final_state, rating = worker._propagate_sync(
            "AAPL", "2026-05-19", {"llm_provider": "test"}, ["market", "kronos"],
        )

    assert captured["seen_kronos_report"] != ""
    assert "Kronos forecast" in captured["seen_kronos_report"]
    assert final_state["kronos_forecast"] is not None
    assert final_state["kronos_forecast"]["ticker"] == "AAPL"
    assert final_state["kronos_status"] == "ok"
    assert rating == "BUY"


def test_propagate_sync_strips_kronos_from_selected_analysts():
    graph, _ = _make_graph_capture_seen_state()
    with patch("api.jobs.TradingAgentsGraph") as graph_cls, \
         patch("api.jobs.fetch_ohlcv", return_value=_ohlcv()), \
         patch("api.jobs.KronosService") as svc_cls:
        graph_cls.return_value = graph
        svc_cls.get.return_value.forecast.return_value = _payload()
        worker = Worker(max_concurrency=1)
        worker._propagate_sync(
            "AAPL", "2026-05-19", {"llm_provider": "test"},
            ["market", "kronos", "news"],
        )
        _, kwargs = graph_cls.call_args
        assert "kronos" not in kwargs["selected_analysts"]
        assert "market" in kwargs["selected_analysts"]
        assert "news" in kwargs["selected_analysts"]


def test_propagate_sync_falls_back_when_insufficient_data():
    graph, captured = _make_graph_capture_seen_state()
    with patch("api.jobs.TradingAgentsGraph", return_value=graph), \
         patch("api.jobs.fetch_ohlcv", side_effect=InsufficientData("only 50 bars")), \
         patch("api.jobs.KronosService") as svc_cls:
        worker = Worker(max_concurrency=1)
        final_state, _ = worker._propagate_sync(
            "AAPL", "2026-05-19", {"llm_provider": "test"}, ["market"],
        )
    assert final_state["kronos_status"] == "insufficient_data"
    assert final_state["kronos_forecast"] is None
    assert "skipped" in captured["seen_kronos_report"].lower() or \
           captured["seen_kronos_report"] == ""


def test_propagate_sync_falls_back_when_model_load_fails():
    graph, captured = _make_graph_capture_seen_state()
    with patch("api.jobs.TradingAgentsGraph", return_value=graph), \
         patch("api.jobs.fetch_ohlcv", return_value=_ohlcv()), \
         patch("api.jobs.KronosService") as svc_cls:
        svc_cls.get.return_value.forecast.side_effect = ModelLoadError("HF down")
        worker = Worker(max_concurrency=1)
        final_state, _ = worker._propagate_sync(
            "AAPL", "2026-05-19", {"llm_provider": "test"}, ["market"],
        )
    assert final_state["kronos_status"] == "load_failed"
    assert final_state["kronos_forecast"] is None
    assert captured["seen_kronos_report"] == ""


def test_monkey_patch_is_restored_on_propagate_exception():
    """Even if propagate() raises, create_initial_state must be restored
    to the original class-level descriptor (no stale instance attribute,
    and calling it returns an unseeded initial state)."""
    graph, _ = _make_graph_capture_seen_state()

    class BoomGraph:
        def __init__(self, base):
            self.propagator = base.propagator

        def propagate(self, ticker, date):
            raise RuntimeError("graph blew up")

    boom = BoomGraph(graph)
    with patch("api.jobs.TradingAgentsGraph", return_value=boom), \
         patch("api.jobs.fetch_ohlcv", return_value=_ohlcv()), \
         patch("api.jobs.KronosService") as svc_cls:
        svc_cls.get.return_value.forecast.return_value = _payload()
        worker = Worker(max_concurrency=1)
        with pytest.raises(RuntimeError):
            worker._propagate_sync(
                "AAPL", "2026-05-19", {"llm_provider": "test"}, ["market"],
            )
    # No stale instance attribute left behind (class-level method restored).
    assert "create_initial_state" not in graph.propagator.__dict__
    # And calling it now produces an *unseeded* state (no kronos_report
    # injection — proving the wrapper closure is gone).
    restored_state = graph.propagator.create_initial_state("AAPL", "2026-05-19")
    assert restored_state["kronos_report"] == ""


def test_propagate_sync_with_kronos_disabled(monkeypatch):
    monkeypatch.setenv("KRONOS_ENABLED", "false")
    graph, captured = _make_graph_capture_seen_state()
    with patch("api.jobs.TradingAgentsGraph", return_value=graph), \
         patch("api.jobs.fetch_ohlcv") as fetch_mock, \
         patch("api.jobs.KronosService") as svc_cls:
        worker = Worker(max_concurrency=1)
        final_state, _ = worker._propagate_sync(
            "AAPL", "2026-05-19", {"llm_provider": "test"}, ["market"],
        )
    fetch_mock.assert_not_called()
    svc_cls.get.assert_not_called()
    assert final_state["kronos_status"] == "disabled"
    assert final_state["kronos_forecast"] is None
    assert captured["seen_kronos_report"] == ""
