"""W1 dimensions-grounded commentary on the PM decision (1 LLM call).

When the model's structured-output path returns no parseable payload — common
on Ollama and OpenRouter free-tier models whose function-calling support is
unreliable — fall back once to a plain ``llm.invoke`` and JSON-parse the
content. Mirrors the scoring fallback in ``api.dimensions.scoring``.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from api.dimensions.schemas import DimensionsCommentary, StockDimensions

logger = logging.getLogger(__name__)


class CommentaryError(RuntimeError):
    pass


_SYSTEM = """You are a quantitative reviewer. Given (a) a portfolio manager's decision
and (b) the standardized dimensions for the stock, give a one-paragraph independent assessment:
- alignment: does the PM's call agree with the dimension signals?
- supporting_dimensions: which factor scores back the PM's view (lowercase factor names)
- conflicting_dimensions: which factor scores push the other way
- risk_flags: dimension-driven risks worth surfacing
- summary: 2-4 sentences"""


_FALLBACK_JSON_USER_SUFFIX = (
    "\n\nRespond with **only** one JSON object (no markdown fences, no commentary) "
    "with keys alignment, supporting_dimensions, conflicting_dimensions, risk_flags, "
    "summary. alignment is one of \"aligned\" | \"partial\" | \"misaligned\"; "
    "supporting_dimensions, conflicting_dimensions, risk_flags are arrays of strings; "
    "summary is a string."
)


def _messages_with_json_fallback_hint(messages: list[dict]) -> list[dict]:
    out = [dict(m) for m in messages]
    if out and out[-1].get("role") == "user":
        last = dict(out[-1])
        last["content"] = str(last.get("content") or "") + _FALLBACK_JSON_USER_SUFFIX
        out[-1] = last
    return out


def _block_content_to_text(content: Any) -> str:
    """Normalize ChatMessage.content (str or OpenAI-style content blocks) to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
                elif "text" in block:
                    parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return str(content)


def _strip_markdown_json_fence(text: str) -> str:
    s = text.strip()
    if not s.startswith("```"):
        return s
    lines = s.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _first_json_object(text: str) -> Dict[str, Any]:
    cleaned = _strip_markdown_json_fence(text)
    decoder = json.JSONDecoder()
    for i, ch in enumerate(cleaned):
        if ch != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(cleaned[i:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    raise ValueError("no JSON object found in model output")


def _commentary_from_invoke_result(result: Any) -> Optional[DimensionsCommentary]:
    """Best-effort coercion for LangChain / provider quirks (dict, AIMessage.parsed, JSON string)."""
    if isinstance(result, DimensionsCommentary):
        return result
    parsed = getattr(result, "parsed", None)
    if isinstance(parsed, DimensionsCommentary):
        return parsed
    if isinstance(parsed, dict):
        try:
            return DimensionsCommentary.model_validate(parsed)
        except Exception:
            pass
    if isinstance(result, dict):
        try:
            return DimensionsCommentary.model_validate(result)
        except Exception:
            pass
    content = getattr(result, "content", None)
    if content is not None:
        text = _block_content_to_text(content).strip()
        if text:
            try:
                return DimensionsCommentary.model_validate(_first_json_object(text))
            except Exception:
                pass
    return None


def build_commentary(
    *,
    dimensions: StockDimensions,
    pm_decision_text: str,
    llm: Any,
) -> DimensionsCommentary:
    payload = {
        "factor_scores": {
            k: getattr(dimensions.factor_scores, k).model_dump()
            for k in ("value", "growth", "quality", "momentum", "low_risk", "sentiment")
        },
        "data_quality_flags": dimensions.data_quality_flags,
    }
    user = (
        f"## PM Decision\n{pm_decision_text}\n\n"
        f"## Dimensions ({dimensions.ticker} as of {dimensions.as_of_date})\n"
        f"```json\n{json.dumps(payload, default=str, indent=2)}\n```"
    )
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]
    result: Any = None
    structured_exc: Optional[Exception] = None
    try:
        structured = llm.with_structured_output(DimensionsCommentary)
        result = structured.invoke(messages)
    except Exception as exc:
        structured_exc = exc
        logger.warning(
            "Dimensions commentary structured invoke failed for ticker=%s as_of_date=%s: %s; "
            "retrying via plain llm.invoke + JSON parse",
            dimensions.ticker,
            dimensions.as_of_date,
            exc,
        )

    if result is not None:
        coerced = _commentary_from_invoke_result(result)
        if coerced is not None:
            return coerced
        logger.warning(
            "Dimensions commentary structured output returned %s for ticker=%s as_of_date=%s; "
            "retrying via plain llm.invoke + JSON parse",
            type(result).__name__,
            dimensions.ticker,
            dimensions.as_of_date,
        )
    elif structured_exc is None:
        logger.warning(
            "Dimensions commentary structured output returned None for ticker=%s as_of_date=%s; "
            "retrying via plain llm.invoke + JSON parse",
            dimensions.ticker,
            dimensions.as_of_date,
        )

    try:
        raw = llm.invoke(_messages_with_json_fallback_hint(messages))
        coerced = _commentary_from_invoke_result(raw)
        if coerced is not None:
            return coerced
        text = _block_content_to_text(getattr(raw, "content", raw)).strip()
        if not text:
            raise ValueError("empty content from llm.invoke")
        return DimensionsCommentary.model_validate(_first_json_object(text))
    except Exception as exc:
        if structured_exc is not None:
            raise CommentaryError(
                f"Commentary fallback failed after structured invoke error: {structured_exc}; "
                f"fallback error: {exc}"
            ) from exc
        raise CommentaryError(
            f"Commentary fallback failed after structured output returned "
            f"{type(result).__name__}: {exc}"
        ) from exc
