"""Phase 2 stub: alternative data analyst (Similarweb / GitHub not wired)."""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.skills import load_skill
from tradingagents.agents.utils.agent_utils import get_instrument_context_from_state, get_language_instruction


def create_alt_data_analyst(llm):
    def alt_data_analyst_node(state):
        instrument_context = get_instrument_context_from_state(state)
        overnight = (state.get("overnight_signal") or "").strip()

        system_message = (
            load_skill("alt_data_analyst")
            + get_language_instruction()
        )

        human_bits = [f"Analyze alternative data context for the ticker."]
        if overnight:
            human_bits.append(f"Overnight signal context:\n{overnight}")

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_message + "\n\n{instrument_context}"),
                MessagesPlaceholder(variable_name="messages"),
                ("human", "\n".join(human_bits)),
            ]
        )

        chain = prompt | llm
        result = chain.invoke(
            {
                "messages": state["messages"],
                "instrument_context": instrument_context,
            }
        )
        report = result.content if hasattr(result, "content") else str(result)
        return {"messages": [result], "alt_data_report": report}

    return alt_data_analyst_node
