from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_news,
    list_akshare_endpoints,
    get_macro_data,
)
from tradingagents.agents.utils.macro_data_tools import AKSHARE_MACRO_DISCOVERY_HINT


def create_policy_analyst(llm):
    """Regulatory, policy, and geopolitical angles relevant to the issuer."""

    def policy_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_news,
            get_global_news,
            list_akshare_endpoints,
            get_macro_data,
        ]

        system_message = (
            "You are the Policy Analyst. Map regulatory, legislative, trade, "
            "sanctions, and geopolitical risks or catalysts that could affect "
            "the company's revenue, costs, or cost of capital. Lead with "
            "company- and sector-specific items from get_news; add broader "
            "policy context from get_global_news when clearly linked. "
            "Use macro tools sparingly when they illuminate policy transmission "
            "(rates, FX, commodities). "
            + AKSHARE_MACRO_DISCOVERY_HINT
            + " "
            "End with one Markdown table: risk/catalyst, mechanism, horizon, "
            "confidence (based only on cited tool facts)."
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
            "policy_report": report,
        }

    return policy_analyst_node
