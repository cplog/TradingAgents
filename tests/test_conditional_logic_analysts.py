"""Conditional routing for arbitrary analyst ids."""

from unittest.mock import MagicMock

import pytest

from tradingagents.graph.conditional_logic import ConditionalLogic


@pytest.mark.unit
def test_should_continue_analyst_routes_to_tools():
    cl = ConditionalLogic()
    msg = MagicMock()
    msg.tool_calls = [MagicMock()]
    state = {"messages": [msg]}
    assert cl.should_continue_analyst("hot_money", state) == "tools_hot_money"


@pytest.mark.unit
def test_should_continue_analyst_routes_to_clear():
    cl = ConditionalLogic()
    msg = MagicMock()
    msg.tool_calls = []
    state = {"messages": [msg]}
    assert cl.should_continue_analyst("hot_money", state) == "Msg Clear Hot Money"

