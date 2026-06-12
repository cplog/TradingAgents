"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

from tradingagents.agents.schemas import ResearchPlan, render_research_plan
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)
        history = state["investment_debate_state"].get("history", "")
        execution_context = (state.get("execution_context") or "").strip()

        investment_debate_state = state["investment_debate_state"]

        execution_note = f"\n\n{execution_context}\n" if execution_context else ""

        prompt = f"""As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate and deliver a clear, actionable investment plan for the trader.

{instrument_context}
{execution_note}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction in the bull thesis; recommend taking or growing the position
- **Overweight**: Constructive view; recommend gradually increasing exposure
- **Hold**: Balanced view; recommend maintaining the current position
- **Underweight**: Cautious view; recommend trimming exposure
- **Sell**: Strong conviction in the bear thesis; recommend exiting or avoiding the position

**Evidence Evaluation Framework:**

Before deciding, explicitly tally the evidence on both sides:

1. List each distinct piece of evidence from the debate (max ~10 items).
2. For each item, note: (a) which side it supports, (b) whether it is a quantitative data point or a qualitative argument, and (c) its approximate weight (minor / moderate / major).
3. Count how many items and how much total weight supports each side.
4. Let the evidence tally guide your rating naturally — do not force a directional stance if the evidence is genuinely balanced.

Rating guidelines based on the evidence tally:
- One side leads by 3+ major evidence items → directional rating (Buy/Sell)
- One side leads by 1-2 major items → Overweight/Underweight
- Evidence is balanced or thin → Hold (this is a valid, honest call)

In **Strategic Actions**, include explicit entry/stop/target levels anchored to the live quote when provided above, and one sentence on what to do if price is already below a proposed stop or above target at decision time.

---

**Debate History:**
{history}""" + get_language_instruction()

        investment_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_research_plan,
            "Research Manager",
        )

        new_investment_debate_state = {
            "judge_decision": investment_plan,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": investment_plan,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": investment_plan,
        }

    return research_manager_node
