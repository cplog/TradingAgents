import logging

from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data,
    query_cached_ohlcv,
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    fetch_hot_news_board,
    get_global_news,
    get_insider_transactions,
    get_news,
    get_prediction_market_snapshot,
    search_data_cache_news,
)
from tradingagents.agents.utils.macro_data_tools import (
    list_akshare_endpoints,
    get_macro_data,
)

logger = logging.getLogger(__name__)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Applied to every agent whose output reaches the saved report —
    analysts, researchers, debaters, research manager, trader, and
    portfolio manager — so a non-English run produces a fully localized
    report rather than a mix of languages.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )


def build_supplementary_analyst_context(state: dict) -> str:
    """Concatenate optional analyst reports for bull/bear prompts."""
    sections = [
        ("Hot Money / flows", "hot_money_report"),
        ("Policy & regulation", "policy_report"),
        ("Lockups & insider overhang", "lockup_report"),
        ("Short-horizon scenarios (Kronos-style)", "kronos_report"),
    ]
    parts: list[str] = []
    for title, key in sections:
        text = (state.get(key) or "").strip()
        if text:
            parts.append(f"### {title}\n{text}")
    if not parts:
        return "(no supplementary analyst reports for this run)"
    return "\n\n".join(parts)


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


def invoke_tool_chain_with_openrouter_fallback(chain, llm, messages):
    """Invoke a tool-bound chain, with OpenRouter fallback when no tool route exists.

    Some OpenRouter routes return:
    ``No endpoints found that support tool use``.
    In that case we retry once without tool binding so the run completes
    (with reduced grounding) instead of crashing the whole graph.
    """
    try:
        return chain.invoke(messages)
    except Exception as exc:
        from tradingagents.dataflows.config import get_config

        provider = str(get_config().get("llm_provider", "")).strip().lower()
        if provider != "openrouter":
            raise
        err = str(exc)
        if "No endpoints found that support tool use" not in err:
            raise
        logger.warning(
            "OpenRouter route rejected tool use; retrying analyst step without tools"
        )
        fallback_instruction = HumanMessage(
            content=(
                "Tool endpoints are unavailable on this route. Continue without tool calls, "
                "state that limitation briefly, and avoid fabricating tool outputs."
            )
        )
        return llm.invoke([*messages, fallback_instruction])
