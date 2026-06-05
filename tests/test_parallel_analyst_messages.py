"""Parallel analyst message scoping (orphan tool message prevention)."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents.utils.agent_utils import (
    messages_for_analyst_branch,
    sanitize_messages_for_tool_api,
    tag_analyst_messages,
)
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.setup import GraphSetup
from tradingagents.agents.utils.agent_states import AgentState


@pytest.mark.unit
def test_sanitize_drops_orphan_tool_message():
    ai = AIMessage(content="", tool_calls=[{
        "name": "get_stock_data",
        "args": {"ticker": "AAPL"},
        "id": "call_1",
        "type": "tool_call",
    }])
    orphan = ToolMessage(content="stale", tool_call_id="other_call")
    cleaned = sanitize_messages_for_tool_api([HumanMessage(content="hi"), orphan, ai])
    assert orphan not in cleaned
    assert ai not in cleaned


@pytest.mark.unit
def test_sanitize_keeps_complete_tool_call_turn():
    ai = AIMessage(content="", tool_calls=[{
        "name": "get_stock_data",
        "args": {"ticker": "AAPL"},
        "id": "call_1",
        "type": "tool_call",
    }])
    tool = ToolMessage(content="data", tool_call_id="call_1")
    cleaned = sanitize_messages_for_tool_api([HumanMessage(content="hi"), ai, tool])
    assert cleaned == [cleaned[0], ai, tool]


@pytest.mark.unit
def test_sanitize_drops_partial_tool_call_turn_before_llm_request():
    ai = AIMessage(content="", tool_calls=[
        {
            "name": "tool_a",
            "args": {},
            "id": "call_a",
            "type": "tool_call",
        },
        {
            "name": "tool_b",
            "args": {},
            "id": "call_b",
            "type": "tool_call",
        },
    ])
    tool_a = ToolMessage(content="a", tool_call_id="call_a")
    next_ai = AIMessage(content="done", tool_calls=[])

    cleaned = sanitize_messages_for_tool_api(
        [HumanMessage(content="hi"), ai, tool_a, next_ai]
    )

    assert ai not in cleaned
    assert tool_a not in cleaned
    assert next_ai in cleaned


@pytest.mark.unit
def test_sanitize_can_keep_pending_final_tool_call_for_tool_node():
    ai = AIMessage(content="", tool_calls=[{
        "name": "get_stock_data",
        "args": {"ticker": "AAPL"},
        "id": "call_1",
        "type": "tool_call",
    }])

    cleaned = sanitize_messages_for_tool_api(
        [HumanMessage(content="hi"), ai],
        allow_incomplete_final_assistant=True,
    )

    assert ai in cleaned


@pytest.mark.unit
def test_messages_for_analyst_branch_excludes_other_branch_tools_on_first_turn(monkeypatch):
    """Policy's first invoke must not see ToolMessages merged from market/news."""
    monkeypatch.setenv("TRADINGAGENTS_PARALLEL_ANALYSTS", "true")
    from tradingagents.dataflows import config as cfg_module

    cfg_module._config = None

    human = HumanMessage(content="hi")
    ai_market = AIMessage(
        content="",
        tool_calls=[{
            "name": "tool_a",
            "args": {"x": "1"},
            "id": "call_a",
            "type": "tool_call",
        }],
    )
    tag_analyst_messages([ai_market], "market")
    tool_market = ToolMessage(content="data", tool_call_id="call_a")

    scoped = messages_for_analyst_branch([human, ai_market, tool_market], "policy")
    assert scoped == [human]
    assert not any(isinstance(m, ToolMessage) for m in scoped)


@pytest.mark.unit
def test_messages_for_analyst_branch_accepts_tuple_human_seed(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_PARALLEL_ANALYSTS", "true")
    from tradingagents.dataflows import config as cfg_module

    cfg_module._config = None

    scoped = messages_for_analyst_branch([("human", "MNSO")], "policy")
    assert len(scoped) == 1
    assert isinstance(scoped[0], HumanMessage)
    assert scoped[0].content == "MNSO"


@pytest.mark.unit
def test_messages_for_analyst_branch_reorders_interleaved_parallel_merge(monkeypatch):
    """Parallel reducers can place other branches between an AI turn and its tools."""
    monkeypatch.setenv("TRADINGAGENTS_PARALLEL_ANALYSTS", "true")
    from tradingagents.dataflows import config as cfg_module

    cfg_module._config = None

    human = HumanMessage(content="hi")
    policy_ai = AIMessage(
        content="",
        tool_calls=[{
            "name": "tool_p",
            "args": {},
            "id": "call_p",
            "type": "tool_call",
        }],
    )
    tag_analyst_messages([policy_ai], "policy")
    market_ai = AIMessage(
        content="",
        tool_calls=[{
            "name": "tool_m",
            "args": {},
            "id": "call_m",
            "type": "tool_call",
        }],
    )
    tag_analyst_messages([market_ai], "market")
    policy_tool = ToolMessage(content="policy data", tool_call_id="call_p")

    scoped = messages_for_analyst_branch(
        [human, policy_ai, market_ai, policy_tool],
        "policy",
    )
    assert scoped == [human, policy_ai, policy_tool]
    assert market_ai not in scoped


@pytest.mark.unit
def test_messages_for_analyst_branch_keeps_multi_turn_transcript(monkeypatch):
    """Earlier assistant turns must keep their tool responses for later LLM calls."""
    monkeypatch.setenv("TRADINGAGENTS_PARALLEL_ANALYSTS", "true")
    from tradingagents.dataflows import config as cfg_module

    cfg_module._config = None

    human = HumanMessage(content="hi")
    ai1 = AIMessage(
        content="",
        tool_calls=[{
            "name": "tool_a",
            "args": {"x": "1"},
            "id": "call_1",
            "type": "tool_call",
        }],
    )
    tag_analyst_messages([ai1], "policy")
    tool1 = ToolMessage(content="data", tool_call_id="call_1")
    ai2 = AIMessage(
        content="",
        tool_calls=[{
            "name": "tool_b",
            "args": {"x": "2"},
            "id": "call_2",
            "type": "tool_call",
        }],
    )
    tag_analyst_messages([ai2], "policy")

    scoped = messages_for_analyst_branch(
        [human, ai1, tool1, ai2],
        "policy",
    )
    assert scoped == [human, ai1, tool1]
    assert ai2 not in scoped


@pytest.mark.unit
def test_messages_for_analyst_branch_filters_cross_branch_tool_calls(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_PARALLEL_ANALYSTS", "true")
    from tradingagents.dataflows import config as cfg_module

    cfg_module._config = None

    human = HumanMessage(content="hi")
    ai_a = AIMessage(
        content="",
        tool_calls=[{
            "name": "tool_a",
            "args": {"x": "1"},
            "id": "call_a",
            "type": "tool_call",
        }],
    )
    tag_analyst_messages([ai_a], "market")
    ai_b = AIMessage(
        content="",
        tool_calls=[{
            "name": "tool_b",
            "args": {"x": "2"},
            "id": "call_b",
            "type": "tool_call",
        }],
    )
    tag_analyst_messages([ai_b], "news")

    scoped = messages_for_analyst_branch(
        [human, ai_a, ai_b],
        "market",
        allow_incomplete_final_assistant=True,
    )
    assert scoped[-1] is ai_a
    assert ai_b not in scoped


@pytest.mark.unit
def test_sequential_mode_still_sanitizes_orphan_tools():
    from tradingagents.dataflows import config as cfg_module

    cfg_module.set_config({"parallel_analysts": False})

    ai = AIMessage(content="", tool_calls=[{
        "name": "get_stock_data",
        "args": {"ticker": "AAPL"},
        "id": "call_1",
        "type": "tool_call",
    }])
    orphan = ToolMessage(content="stale", tool_call_id="other_call")
    scoped = messages_for_analyst_branch(
        [HumanMessage(content="hi"), orphan, ai],
        "market",
    )
    assert orphan not in scoped
    assert ai not in scoped


@pytest.mark.unit
def test_should_continue_analyst_uses_branch_last_message(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_PARALLEL_ANALYSTS", "true")
    from tradingagents.dataflows import config as cfg_module

    cfg_module._config = None

    cl = ConditionalLogic()
    human = HumanMessage(content="hi")
    ai_a = AIMessage(
        content="",
        tool_calls=[{
            "name": "tool_a",
            "args": {"x": "1"},
            "id": "call_a",
            "type": "tool_call",
        }],
    )
    tag_analyst_messages([ai_a], "market")
    ai_b = AIMessage(
        content="done",
        tool_calls=[],
    )
    tag_analyst_messages([ai_b], "news")

    state = {"messages": [human, ai_a, ai_b]}
    assert cl.should_continue_analyst("market", state) == "tools_market"


@pytest.mark.unit
def test_should_continue_analyst_routes_to_clear_when_branch_finished(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_PARALLEL_ANALYSTS", "true")
    from tradingagents.dataflows import config as cfg_module

    cfg_module._config = None

    cl = ConditionalLogic()
    human = HumanMessage(content="hi")
    ai_a = AIMessage(content="done", tool_calls=[])
    tag_analyst_messages([ai_a], "market")
    ai_b = AIMessage(
        content="",
        tool_calls=[{
            "name": "tool_b",
            "args": {},
            "id": "call_b",
            "type": "tool_call",
        }],
    )
    tag_analyst_messages([ai_b], "news")

    state = {"messages": [human, ai_a, ai_b]}
    assert cl.should_continue_analyst("market", state) == "Msg Clear Market"


@pytest.mark.unit
def test_parallel_analysts_join_before_debate(monkeypatch):
    """All analyst branches must converge before Bull Researcher runs once."""
    from tradingagents.graph import setup as setup_module

    def make_analyst(report_key: str):
        def factory(_llm):
            def node(_state):
                return {
                    "messages": [AIMessage(content=f"{report_key} done", tool_calls=[])],
                    report_key: "done",
                }

            return node

        return factory

    def bull_factory(_llm):
        def node(state):
            debate = state["investment_debate_state"]
            return {
                "investment_debate_state": {
                    **debate,
                    "current_response": "Bull Analyst: once",
                    "count": debate["count"] + 1,
                }
            }

        return node

    def bear_factory(_llm):
        def node(state):
            return {"investment_debate_state": state["investment_debate_state"]}

        return node

    def manager_factory(_llm):
        def node(_state):
            return {"investment_plan": "plan"}

        return node

    def passthrough_factory(key: str, value: str):
        def factory(_llm):
            def node(_state):
                return {key: value}

            return node

        return factory

    monkeypatch.setattr(
        setup_module,
        "ANALYST_NODE_FACTORIES",
        {
            "market": make_analyst("market_report"),
            "news": make_analyst("news_report"),
        },
    )
    monkeypatch.setattr(setup_module, "create_bull_researcher", bull_factory)
    monkeypatch.setattr(setup_module, "create_bear_researcher", bear_factory)
    monkeypatch.setattr(setup_module, "create_research_manager", manager_factory)
    monkeypatch.setattr(
        setup_module,
        "create_trader",
        passthrough_factory("trader_investment_plan", "trade"),
    )
    monkeypatch.setattr(
        setup_module,
        "create_aggressive_debator",
        passthrough_factory("risk_debate_state", {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "history": "",
            "latest_speaker": "Aggressive",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "judge_decision": "",
            "count": 3,
        }),
    )
    monkeypatch.setattr(
        setup_module,
        "create_conservative_debator",
        passthrough_factory("risk_debate_state", {}),
    )
    monkeypatch.setattr(
        setup_module,
        "create_neutral_debator",
        passthrough_factory("risk_debate_state", {}),
    )
    monkeypatch.setattr(
        setup_module,
        "create_portfolio_manager",
        passthrough_factory("final_trade_decision", "Hold"),
    )
    monkeypatch.setattr(
        setup_module,
        "create_dimensions_snapshot_node",
        lambda _llm, _config: (lambda _state: {"dimensions_summary": "ok"}),
    )

    graph_setup = GraphSetup(
        quick_thinking_llm=object(),
        deep_thinking_llm=object(),
        tool_nodes={"market": ToolNode([]), "news": ToolNode([])},
        conditional_logic=ConditionalLogic(max_debate_rounds=0, max_risk_discuss_rounds=1),
        config={"parallel_analysts": True},
    )
    graph = graph_setup.setup_graph(["market", "news"]).compile()

    out = graph.invoke({
        "messages": [HumanMessage(content="MNSO")],
        "company_of_interest": "MNSO",
        "asset_type": "stock",
        "instrument_context": "",
        "trade_date": "2026-06-04",
        "sender": "",
        "market_report": "",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "hot_money_report": "",
        "policy_report": "",
        "lockup_report": "",
        "kronos_report": "",
        "investment_debate_state": {
            "bull_history": "",
            "bear_history": "",
            "history": "",
            "current_response": "",
            "judge_decision": "",
            "count": 0,
        },
        "investment_plan": "",
        "trader_investment_plan": "",
        "risk_debate_state": {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "history": "",
            "latest_speaker": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "judge_decision": "",
            "count": 0,
        },
        "final_trade_decision": "",
        "past_context": "",
    })

    assert out["investment_debate_state"]["count"] == 1


@pytest.mark.unit
def test_investment_debate_state_reducer_handles_concurrent_writes():
    """Concurrent debate writes should merge instead of raising InvalidUpdateError."""

    def route(_state):
        return ["a", "b"]

    def writer(label: str):
        def node(state):
            debate = state["investment_debate_state"]
            return {
                "investment_debate_state": {
                    **debate,
                    "history": label,
                    "current_response": label,
                    "count": debate["count"] + 1,
                }
            }

        return node

    graph = StateGraph(AgentState)
    graph.add_node("a", writer("a"))
    graph.add_node("b", writer("b"))
    graph.add_conditional_edges(START, route, ["a", "b"])
    graph.add_edge("a", END)
    graph.add_edge("b", END)
    compiled = graph.compile()

    out = compiled.invoke({
        "messages": [HumanMessage(content="MNSO")],
        "company_of_interest": "MNSO",
        "asset_type": "stock",
        "instrument_context": "",
        "trade_date": "2026-06-05",
        "sender": "",
        "market_report": "",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "hot_money_report": "",
        "policy_report": "",
        "lockup_report": "",
        "kronos_report": "",
        "investment_debate_state": {
            "bull_history": "",
            "bear_history": "",
            "history": "",
            "current_response": "",
            "judge_decision": "",
            "count": 0,
        },
        "investment_plan": "",
        "trader_investment_plan": "",
        "risk_debate_state": {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "history": "",
            "latest_speaker": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "judge_decision": "",
            "count": 0,
        },
        "final_trade_decision": "",
        "past_context": "",
    })

    assert out["investment_debate_state"]["count"] == 1
    assert out["investment_debate_state"]["current_response"] in {"a", "b"}
