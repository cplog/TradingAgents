import functools
import logging
from typing import Any, Mapping, Optional

import yfinance as yf
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

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


def _parallel_analysts_enabled() -> bool:
    from tradingagents.dataflows.config import get_config

    return bool(get_config().get("parallel_analysts", False))


def _tool_call_id(tool_call: Any) -> str:
    if isinstance(tool_call, dict):
        return str(tool_call.get("id") or "")
    return str(getattr(tool_call, "id", "") or "")


def _coerce_seed_human(messages: list[Any]) -> Optional[HumanMessage]:
    """Return the initial user message for analyst prompts."""
    for message in messages:
        if isinstance(message, HumanMessage):
            return message
        if isinstance(message, tuple) and len(message) >= 2:
            role, content = message[0], message[1]
            if str(role).lower() in {"human", "user"}:
                return HumanMessage(content=str(content))
    return None


def _message_analyst_id(message: Any) -> Optional[str]:
    additional = getattr(message, "additional_kwargs", None) or {}
    if isinstance(additional, dict):
        value = additional.get("analyst_id")
        return str(value) if value else None
    return None


def tag_analyst_messages(messages: list[Any], analyst_id: str) -> list[Any]:
    """Tag assistant messages so parallel branches can be disambiguated after merge."""
    for message in messages:
        if isinstance(message, AIMessage):
            additional = dict(message.additional_kwargs or {})
            additional["analyst_id"] = analyst_id
            message.additional_kwargs = additional
    return messages


def sanitize_messages_for_tool_api(
    messages: list[Any],
    *,
    allow_incomplete_final_assistant: bool = False,
) -> list[Any]:
    """Return a provider-valid tool-call transcript.

    Chat-completions APIs require every assistant ``tool_calls`` turn to be
    followed immediately by one tool message for each call id. Parallel branch
    merges can leave partial turns in shared history, so rebuild the transcript
    in small assistant/tool-call groups instead of only dropping orphan tools.

    ``ToolNode`` is the one valid consumer of an incomplete final assistant
    message: it needs that pending turn in order to execute the requested tools.
    LLM calls should keep the default and omit incomplete turns.
    """
    if not messages:
        return messages

    sanitized: list[Any] = []
    index = 0
    total = len(messages)

    while index < total:
        message = messages[index]
        if isinstance(message, ToolMessage):
            index += 1
            continue

        if not isinstance(message, AIMessage) or not message.tool_calls:
            sanitized.append(message)
            index += 1
            continue

        pending_tool_ids = [
            call_id
            for call_id in (_tool_call_id(tc) for tc in (message.tool_calls or []))
            if call_id
        ]
        if not pending_tool_ids:
            if message.tool_calls:
                stripped = message.model_copy()
                stripped.tool_calls = []
                if stripped.content:
                    sanitized.append(stripped)
            else:
                sanitized.append(message)
            index += 1
            continue

        group: list[Any] = [message]
        remaining = set(pending_tool_ids)
        for cursor in range(index + 1, total):
            tool_message = messages[cursor]
            if not isinstance(tool_message, ToolMessage):
                continue
            tool_call_id = str(getattr(tool_message, "tool_call_id", "") or "")
            if tool_call_id in remaining:
                group.append(tool_message)
                remaining.discard(tool_call_id)

        if not remaining or (
            allow_incomplete_final_assistant and index == total - 1
        ):
            sanitized.extend(group)

        index += 1

    return sanitized


def messages_for_analyst_branch(
    messages: list[Any],
    analyst_id: str,
    *,
    allow_incomplete_final_assistant: bool = False,
) -> list[Any]:
    """Subset of merged history that belongs to one parallel analyst branch."""
    if not messages:
        return messages

    if not _parallel_analysts_enabled():
        return sanitize_messages_for_tool_api(
            list(messages),
            allow_incomplete_final_assistant=allow_incomplete_final_assistant,
        )

    seed_human = _coerce_seed_human(messages)

    scoped: list[Any] = []
    if seed_human is not None:
        scoped.append(seed_human)

    for message in messages:
        if isinstance(message, (HumanMessage, tuple)):
            continue
        if not isinstance(message, AIMessage):
            continue
        if _message_analyst_id(message) != analyst_id:
            continue
        scoped.append(message)
        turn_call_ids = {
            call_id
            for call_id in (_tool_call_id(tc) for tc in (message.tool_calls or []))
            if call_id
        }
        if not turn_call_ids:
            continue
        for tool_message in messages:
            if not isinstance(tool_message, ToolMessage):
                continue
            tool_call_id = str(getattr(tool_message, "tool_call_id", "") or "")
            if tool_call_id in turn_call_ids and tool_message not in scoped:
                scoped.append(tool_message)

    return sanitize_messages_for_tool_api(
        scoped,
        allow_incomplete_final_assistant=allow_incomplete_final_assistant,
    )


def prepare_analyst_work_state(state: Mapping[str, Any], analyst_id: str) -> dict[str, Any]:
    """Return state with a branch-scoped message list for analyst/tool LLM calls."""
    if not _parallel_analysts_enabled():
        messages = sanitize_messages_for_tool_api(list(state.get("messages") or []))
        return {**dict(state), "messages": messages}
    return {
        **dict(state),
        "messages": messages_for_analyst_branch(
            list(state.get("messages") or []),
            analyst_id,
        ),
    }


def create_scoped_tool_node(analyst_id: str, tool_node: Any) -> Any:
    """Wrap ToolNode so parallel merges do not route the wrong branch's tool_calls."""

    def scoped_tool_node(state: Mapping[str, Any]) -> dict[str, Any]:
        if not _parallel_analysts_enabled():
            return tool_node.invoke(state)
        scoped_state = {
            **dict(state),
            "messages": messages_for_analyst_branch(
                list(state.get("messages") or []),
                analyst_id,
                allow_incomplete_final_assistant=True,
            ),
        }
        result = tool_node.invoke(scoped_state)
        if isinstance(result, dict) and "messages" in result:
            tag_analyst_messages(result["messages"], analyst_id)
        return result

    return scoped_tool_node


def wrap_analyst_node(analyst_id: str, analyst_node: Any) -> Any:
    """Scope merged messages and tag assistant outputs for parallel analyst runs."""

    def wrapped_node(state: Mapping[str, Any]) -> dict[str, Any]:
        work_state = prepare_analyst_work_state(state, analyst_id)
        result = analyst_node(work_state)
        if isinstance(result, dict) and result.get("messages"):
            tag_analyst_messages(result["messages"], analyst_id)
        return result

    return wrapped_node


def create_msg_passthrough():
    """No-op graph node for branches that should not mutate shared messages."""

    def pass_messages(state):
        return {}

    return pass_messages


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add a context-anchored placeholder.

        The placeholder must not be a bare ``"Continue"``: some
        OpenAI-compatible providers interpret that literally as the user task
        and produce output about the word "continue" instead of analysing the
        instrument (#888). Anchoring it to the resolved instrument context and
        date keeps the next analyst on-task even if the provider treats the
        placeholder as a standalone request.
        """
        messages = state["messages"]
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        instrument_context = get_instrument_context_from_state(state)
        trade_date = state.get("trade_date", "the requested date")
        placeholder = HumanMessage(
            content=(
                f"Proceed with your assigned analysis for this workflow. "
                f"{instrument_context} The analysis date is {trade_date}."
            )
        )
        return {"messages": removal_operations + [placeholder]}

    return delete_messages


def _tool_routing_rejected(exc: Exception) -> bool:
    """True when the provider/model rejected LangChain tool binding."""
    err = str(exc).lower()
    if "no endpoints found that support tool use" in err:
        return True
    # NVIDIA NIM (integrate.api.nvidia.com): Function '<uuid>': Not found for account '...'
    if "function '" in err and "not found" in err:
        return True
    if "does not support tool" in err:
        return True
    return False


def invoke_tool_chain_with_openrouter_fallback(chain, llm, messages):
    """Invoke a tool-bound chain, falling back when the route rejects tool use.

    OpenRouter may return ``No endpoints found that support tool use``.
    NVIDIA NIM returns HTTP 404 with ``Function '<uuid>': Not found for account``.
    In those cases we retry once without tool binding so the run completes
    (with reduced grounding) instead of crashing the whole graph.
    """
    messages = sanitize_messages_for_tool_api(list(messages))
    try:
        return chain.invoke(messages)
    except Exception as exc:
        from tradingagents.dataflows.config import get_config

        provider = str(get_config().get("llm_provider", "")).strip().lower()
        if provider not in ("openrouter", "nvidia") or not _tool_routing_rejected(exc):
            raise
        logger.warning(
            "%s route rejected tool use (%s); retrying analyst step without tools",
            provider,
            exc,
        )
        fallback_instruction = HumanMessage(
            content=(
                "Tool endpoints are unavailable on this route. Continue without tool calls, "
                "state that limitation briefly, and avoid fabricating tool outputs."
            )
        )
        return llm.invoke([*messages, fallback_instruction])
