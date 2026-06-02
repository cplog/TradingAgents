from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.skills import load_skill
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_macro_data,
    get_indicators,
    invoke_tool_chain_with_openrouter_fallback,
    get_language_instruction,
    list_akshare_endpoints,
    get_stock_data,
)
from tradingagents.agents.utils.overnight_tools import (
    compute_overnight_signal_tool,
    scan_us_market_drops,
)
from tradingagents.dataflows.config import get_config


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])
        execution_context = (state.get("execution_context") or "").strip()
        execution_block = f"\n\n{execution_context}\n" if execution_context else ""

        tools = [
            get_stock_data,
            get_indicators,
            list_akshare_endpoints,
            get_macro_data,
            compute_overnight_signal_tool,
            scan_us_market_drops,
        ]

        system_message = (
            load_skill("market_analyst")
            + get_language_instruction()
            + execution_block
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
        result = invoke_tool_chain_with_openrouter_fallback(
            chain, llm, state["messages"]
        )

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "market_report": report,
        }

    return market_analyst_node
