# TradingAgents/graph/setup.py

from typing import Any, Callable, Dict, Optional
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Send

from tradingagents.agents import (
    create_aggressive_debator,
    create_alt_data_analyst,
    create_bear_researcher,
    create_bull_researcher,
    create_conservative_debator,
    create_fundamentals_analyst,
    create_hot_money_analyst,
    create_kronos_analyst,
    create_lockup_analyst,
    create_market_analyst,
    create_msg_delete,
    create_neutral_debator,
    create_news_analyst,
    create_policy_analyst,
    create_portfolio_manager,
    create_research_manager,
    create_sentiment_analyst,
    create_trader,
)
from tradingagents.agents.dimensions_snapshot import create_dimensions_snapshot_node
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.analyst_labels import (
    analyst_graph_analyst_node_name,
    analyst_msg_clear_node_name,
)

from .conditional_logic import ConditionalLogic

AnalystNodeFactory = Callable[[Any], Callable[..., Dict[str, Any]]]

ANALYST_NODE_FACTORIES: Dict[str, AnalystNodeFactory] = {
    "market": create_market_analyst,
    "social": create_sentiment_analyst,
    "news": create_news_analyst,
    "fundamentals": create_fundamentals_analyst,
    "hot_money": create_hot_money_analyst,
    "policy": create_policy_analyst,
    "lockup": create_lockup_analyst,
    "kronos": create_kronos_analyst,
    "alt_data": create_alt_data_analyst,
}


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
        config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic
        self.config: Dict[str, Any] = dict(config or {})
        self.selected_analysts: list[str] = []

    def _route_to_analysts(self, state: AgentState) -> list[Send]:
        """Fan out to all selected analysts in parallel via LangGraph Send."""
        return [
            Send(analyst_graph_analyst_node_name(aid), state)
            for aid in self.selected_analysts
        ]

    def setup_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals"]
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): Analyst ids in execution order. Core ids:
                market, social, news, fundamentals. Optional: hot_money, policy,
                lockup, kronos.
        """
        self.selected_analysts = selected_analysts

        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        unknown = [a for a in selected_analysts if a not in ANALYST_NODE_FACTORIES]
        if unknown:
            raise ValueError(
                "Trading Agents Graph Setup Error: unknown analyst(s): "
                + ", ".join(unknown)
            )

        analyst_nodes: Dict[str, Any] = {}
        delete_nodes: Dict[str, Any] = {}
        tool_nodes_map: Dict[str, ToolNode] = {}

        for analyst_id in selected_analysts:
            analyst_nodes[analyst_id] = ANALYST_NODE_FACTORIES[analyst_id](
                self.quick_thinking_llm
            )
            delete_nodes[analyst_id] = create_msg_delete()
            tool_nodes_map[analyst_id] = self.tool_nodes[analyst_id]

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm)
        research_manager_node = create_research_manager(self.deep_thinking_llm)
        trader_node = create_trader(self.quick_thinking_llm)

        # Create risk analysis nodes
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm)

        dimensions_snapshot_node = create_dimensions_snapshot_node(
            self.quick_thinking_llm, self.config
        )

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(analyst_graph_analyst_node_name(analyst_type), node)
            workflow.add_node(
                analyst_msg_clear_node_name(analyst_type),
                delete_nodes[analyst_type],
            )
            workflow.add_node(f"tools_{analyst_type}", tool_nodes_map[analyst_type])

        # Add other nodes
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)
        workflow.add_node("Dimensions Snapshot", dimensions_snapshot_node)

        # Analyst wiring: sequential (default) or parallel via Send
        parallel = self.config.get("parallel_analysts", False)

        if parallel:
            # Parallel: START fans out to all analysts via Send
            workflow.add_conditional_edges(
                START, self._route_to_analysts
            )
        else:
            # Sequential: chain analysts one after another
            first_analyst = selected_analysts[0]
            workflow.add_edge(
                START, analyst_graph_analyst_node_name(first_analyst)
            )

        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = analyst_graph_analyst_node_name(analyst_type)
            current_tools = f"tools_{analyst_type}"
            current_clear = analyst_msg_clear_node_name(analyst_type)

            workflow.add_conditional_edges(
                current_analyst,
                lambda state, aid=analyst_type: self.conditional_logic.should_continue_analyst(
                    aid, state
                ),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            if parallel:
                # In parallel mode, all analysts converge at Dimensions Snapshot
                workflow.add_edge(current_clear, "Dimensions Snapshot")
            else:
                if i < len(selected_analysts) - 1:
                    next_analyst = analyst_graph_analyst_node_name(
                        selected_analysts[i + 1]
                    )
                    workflow.add_edge(current_clear, next_analyst)
                else:
                    workflow.add_edge(current_clear, "Dimensions Snapshot")

        workflow.add_edge("Dimensions Snapshot", "Bull Researcher")

        # Add remaining edges
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")
        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Conservative Analyst": "Conservative Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Aggressive Analyst": "Aggressive Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )

        workflow.add_edge("Portfolio Manager", END)

        return workflow
