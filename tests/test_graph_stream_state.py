"""Tests for streamed LangGraph state merging."""

from __future__ import annotations

from tradingagents.graph.job_control import GraphStepHooks
from tradingagents.graph.trading_graph import TradingAgentsGraph


class _FakeGraph:
    def stream(self, init_state, **args):
        yield {"Market Analyst": {"market_report": "ok"}}
        yield {"Portfolio Manager": {"final_trade_decision": "Buy"}}


class _FakePropagator:
    def get_graph_args(self, callbacks=None):
        return {"stream_mode": "updates", "config": {}}


def test_stream_graph_preserves_initial_state_keys():
    ta = TradingAgentsGraph.__new__(TradingAgentsGraph)
    ta.graph = _FakeGraph()
    ta.propagator = _FakePropagator()

    init = {
        "company_of_interest": "AAPL",
        "trade_date": "2026-06-06",
        "market_report": "",
        "final_trade_decision": "",
    }
    hooks = GraphStepHooks(on_step=lambda _n: None)
    out = ta._stream_graph(init, {"stream_mode": "updates"}, hooks)

    assert out["company_of_interest"] == "AAPL"
    assert out["trade_date"] == "2026-06-06"
    assert out["market_report"] == "ok"
    assert out["final_trade_decision"] == "Buy"
