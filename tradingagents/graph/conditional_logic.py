# TradingAgents/graph/conditional_logic.py

from typing import Optional

from tradingagents.agents.utils.agent_states import AgentState


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(
        self,
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        convergence_checker=None,
        debate_scorer_enabled=False,
    ):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds
        self.convergence_checker = convergence_checker
        self.debate_scorer_enabled = debate_scorer_enabled

    def should_continue_analyst(self, analyst_key: str, state: AgentState) -> str:
        """Route tool-loop vs message-clear for any analyst id (incl. snake_case)."""
        from tradingagents.agents.utils.agent_utils import (
            messages_for_analyst_branch,
            _parallel_analysts_enabled,
        )
        from tradingagents.agents.utils.analyst_labels import analyst_title_words

        messages = state["messages"]
        if _parallel_analysts_enabled():
            messages = messages_for_analyst_branch(
                messages,
                analyst_key,
                allow_incomplete_final_assistant=True,
            ) or messages
        last_message = messages[-1]
        if last_message.tool_calls:
            return f"tools_{analyst_key}"
        return f"Msg Clear {analyst_title_words(analyst_key)}"

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue."""

        if (
            state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
        ):  # hard ceiling
            return "Debate Scorer" if self.debate_scorer_enabled else "Research Manager"

        # Semantic termination: check convergence after full rounds
        if (
            self.convergence_checker
            and self.convergence_checker.check_bull_bear(state)
        ):
            return "Debate Scorer" if self.debate_scorer_enabled else "Research Manager"

        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue."""
        if (
            state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds
        ):  # hard ceiling
            return "Portfolio Manager"

        # Semantic termination: check convergence after full rounds
        if (
            self.convergence_checker
            and self.convergence_checker.check_risk(state)
        ):
            return "Portfolio Manager"

        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
