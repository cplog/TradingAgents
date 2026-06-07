"""Smoke tests for Options Strategist graph wiring."""
from __future__ import annotations

from unittest.mock import MagicMock

from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.setup import GraphSetup


def _mock_tool_nodes(analyst_ids):
    from langgraph.prebuilt import ToolNode

    return {aid: ToolNode([]) for aid in analyst_ids}


def test_options_strategist_disabled_by_default():
    setup = GraphSetup(
        quick_thinking_llm=MagicMock(),
        deep_thinking_llm=MagicMock(),
        tool_nodes=_mock_tool_nodes(["market", "social", "news", "fundamentals"]),
        conditional_logic=ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1),
        config={"options_strategist_enabled": False},
    )
    workflow = setup.setup_graph()
    nodes = list(workflow.nodes.keys())
    assert "Options Strategist" not in nodes


def test_options_strategist_enabled():
    setup = GraphSetup(
        quick_thinking_llm=MagicMock(),
        deep_thinking_llm=MagicMock(),
        tool_nodes=_mock_tool_nodes(["market", "social", "news", "fundamentals"]),
        conditional_logic=ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1),
        config={"options_strategist_enabled": True},
    )
    workflow = setup.setup_graph()
    nodes = list(workflow.nodes.keys())
    assert "Options Strategist" in nodes
    # Verify edge PM -> OS -> END exists
    edge_targets = {dst for src, dst in workflow.edges if src == "Portfolio Manager"}
    assert "Options Strategist" in edge_targets
    end_targets = {dst for src, dst in workflow.edges if src == "Options Strategist"}
    assert "__end__" in end_targets or any("END" in str(e) for e in end_targets)
