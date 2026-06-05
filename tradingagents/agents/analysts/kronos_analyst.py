from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.skills import load_skill
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_indicators,
    get_language_instruction,
    get_stock_data,
    sanitize_messages_for_tool_api,
)


def create_kronos_analyst(llm):
    """Short-horizon scenario paths from recent price/volatility (LLM synthesis).

    This is not the external Kronos ML model; it is a structured scenario brief
    grounded in tool-returned OHLCV and indicators.
    """

    def kronos_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_stock_data,
            get_indicators,
        ]

        system_message = (
            load_skill("kronos_analyst")
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(sanitize_messages_for_tool_api(state["messages"]))

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "kronos_report": report,
        }

    return kronos_analyst_node
