import functools
import logging
from typing import Any, Mapping, Optional

import yfinance as yf
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


def _clean_identity_value(value: Any) -> Optional[str]:
    """Return a trimmed string, or None for empty / placeholder-ish values."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.lower() in {"none", "n/a", "nan", "null"}:
        return None
    return cleaned


@functools.lru_cache(maxsize=256)
def resolve_instrument_identity(ticker: str) -> dict:
    """Resolve deterministic identity metadata (company name, sector, …) for a ticker.

    This exists to stop the pipeline from hallucinating a *different* company
    when a chart pattern suggests a different industry than the real one
    (#814): without a ground-truth name, the market analyst would pattern-match
    the price action to a narrative and invent an identity that then cascaded
    through every downstream agent.

    Best-effort by design: if yfinance is unavailable, rate-limited, or doesn't
    recognise the ticker, we return ``{}`` and the caller falls back to
    ticker-only context rather than failing before analysis starts. Cached so
    the lookup happens at most once per ticker per process.
    """
    try:
        info = yf.Ticker(ticker.upper()).info or {}
    except Exception as exc:  # noqa: BLE001 — fail open, never block the run
        logger.debug("Could not resolve instrument identity for %s: %s", ticker, exc)
        return {}

    identity: dict[str, str] = {}
    company_name = _clean_identity_value(info.get("longName")) or _clean_identity_value(
        info.get("shortName")
    )
    if company_name:
        identity["company_name"] = company_name
    for source_key, target_key in (
        ("sector", "sector"),
        ("industry", "industry"),
        ("exchange", "exchange"),
        ("quoteType", "quote_type"),
    ):
        value = _clean_identity_value(info.get(source_key))
        if value:
            identity[target_key] = value
    return identity


def build_instrument_context(
    ticker: str,
    asset_type: str = "stock",
    identity: Optional[Mapping[str, str]] = None,
) -> str:
    """Describe the exact instrument so agents preserve identity and ticker.

    When ``identity`` is provided (resolved deterministically via
    :func:`resolve_instrument_identity`), the company name and business
    classification are injected so agents anchor to the real company rather
    than pattern-matching the price chart to a wrong one (#814).
    """
    is_crypto = asset_type == "crypto"
    instrument_label = "asset" if is_crypto else "instrument"
    context = (
        f"The {instrument_label} to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )

    details = []
    if identity:
        name = identity.get("company_name") or identity.get("name")
        if name:
            details.append(f"{'Name' if is_crypto else 'Company'}: {name}")
        sector, industry = identity.get("sector"), identity.get("industry")
        if sector and industry:
            details.append(f"Business classification: {sector} / {industry}")
        elif sector:
            details.append(f"Sector: {sector}")
        elif industry:
            details.append(f"Industry: {industry}")
        if identity.get("exchange"):
            details.append(f"Exchange: {identity['exchange']}")

    if details:
        context += (
            f" Resolved identity: {'; '.join(details)}. "
            "Do not substitute a different company or ticker unless a tool "
            "result explicitly disproves this resolved identity."
        )

    if is_crypto:
        context += (
            " Treat it as a crypto asset rather than a company, and do not "
            "assume company fundamentals are available."
        )
    return context


def get_instrument_context_from_state(state: Mapping[str, Any]) -> str:
    """Return the instrument context for the current run.

    Prefers the identity-resolved context computed once at run start and
    stored on the state. Falls back to a ticker-only context — with no
    network lookup — when the state was constructed without it.
    """
    ticker = state.get("company_of_interest", "")
    asset_type = state.get("asset_type", "stock")
    instrument_context = state.get("instrument_context", "")
    if instrument_context:
        return instrument_context
    return build_instrument_context(ticker, asset_type)


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
