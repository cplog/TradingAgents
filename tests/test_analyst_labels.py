"""Unit tests for LangGraph analyst node label helpers."""

import pytest

from tradingagents.agents.utils.analyst_labels import (
    analyst_graph_analyst_node_name,
    analyst_msg_clear_node_name,
    analyst_title_words,
)


@pytest.mark.unit
def test_hot_money_labels():
    assert analyst_title_words("hot_money") == "Hot Money"
    assert analyst_graph_analyst_node_name("hot_money") == "Hot Money Analyst"
    assert analyst_msg_clear_node_name("hot_money") == "Msg Clear Hot Money"


@pytest.mark.unit
def test_social_remains_single_word_title():
    assert analyst_graph_analyst_node_name("social") == "Social Analyst"

