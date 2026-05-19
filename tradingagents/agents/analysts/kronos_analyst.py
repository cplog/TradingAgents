from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_indicators,
    get_language_instruction,
    get_stock_data,
)


def create_kronos_analyst(llm):
    """Short-horizon scenario paths from recent price/volatility (LLM synthesis).

    This is not the external Kronos ML model; it is a structured scenario brief
    grounded in tool-returned OHLCV and indicators.
    """

    def kronos_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_stock_data,
            get_indicators,
        ]

        system_message = (
            "You are the Kronos-style Scenario Analyst (tool-grounded, not a "
            "trained forecaster). After pulling recent OHLCV via get_stock_data, "
            "compute complementary indicators (e.g. rsi, macd, atr, boll) with "
            "get_indicators to characterize volatility and momentum. Produce "
            "3–5 distinct near-term price paths (base, bullish, bearish, "
            "high-volatility) with explicit assumptions tied to numbers from "
            "tools only—no fabricated levels or dates. Include a brief "
            "disclaimer that paths are heuristic scenarios, not predictions. "
            "End with one Markdown table listing scenario, trigger conditions "
            "(from data), and invalidation signals."
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
        result = chain.invoke(state["messages"])

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "kronos_report": report,
        }

    return kronos_analyst_node
