"""Single structured-output LLM call producing PillarScores."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from api.dimensions.schemas import FactSnapshot, PillarScores

logger = logging.getLogger(__name__)


class PillarScoringError(RuntimeError):
    pass


_SYSTEM = """You are a quantitative research analyst. Given (a) a stock's deterministic facts
and (b) analyst reports — the core four (Market, Sentiment, News, Fundamentals) plus any
supplementary sections provided — score 16 sub-dimensions
on a 1-5 scale with a one-sentence rationale per score.

CRITICAL: `volatility_risk` and `surprise_risk` are inverted — HIGHER score means LOWER risk.
For all other dimensions, higher score means stronger/better.

Be calibrated. 3 = average; 5 is reserved for genuinely standout cases."""

_SUPPLEMENTARY_REPORT_KEYS = (
    ("hot_money", "Hot Money"),
    ("policy", "Policy"),
    ("lockup", "Lockup"),
    ("kronos", "Kronos scenarios"),
)


_FALLBACK_JSON_USER_SUFFIX = (
    "\n\nRespond with **only** one JSON object (no markdown fences, no commentary) "
    "with keys market, sentiment, news, fundamentals. Each nested object matches "
    'the schema (e.g. market.trend.score integer 1–5, market.trend.rationale string).'
)


def _messages_with_json_fallback_hint(messages: list[dict]) -> list[dict]:
    out = [dict(m) for m in messages]
    if out and out[-1].get("role") == "user":
        last = dict(out[-1])
        last["content"] = str(last.get("content") or "") + _FALLBACK_JSON_USER_SUFFIX
        out[-1] = last
    return out


def _build_prompt(facts: FactSnapshot, reports: Dict[str, str]) -> list[dict]:
    facts_json = json.dumps(facts.model_dump(), default=str, indent=2)
    body = [f"## Facts\n```json\n{facts_json}\n```"]
    for key in ("market", "social", "news", "fundamentals"):
        text = reports.get(key) or "(no report available)"
        body.append(f"## {key.title()} Analyst Report\n{text}")
    for key, title in _SUPPLEMENTARY_REPORT_KEYS:
        text = (reports.get(key) or "").strip()
        if text:
            body.append(f"## {title} Analyst Report (supplementary)\n{text}")
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": "\n\n".join(body)},
    ]


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
    """Parse the first top-level JSON object in ``text`` (prose / fences tolerated)."""
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


def _pillar_scores_from_invoke_result(result: Any) -> Optional[PillarScores]:
    """Best-effort coercion for LangChain / provider quirks (dict, AIMessage.parsed, JSON string)."""
    if isinstance(result, PillarScores):
        return result
    parsed = getattr(result, "parsed", None)
    if isinstance(parsed, PillarScores):
        return parsed
    if isinstance(parsed, dict):
        try:
            return PillarScores.model_validate(parsed)
        except Exception:
            pass
    if isinstance(result, dict):
        try:
            return PillarScores.model_validate(result)
        except Exception:
            pass
    content = getattr(result, "content", None)
    if content is not None:
        text = _block_content_to_text(content).strip()
        if text:
            try:
                return PillarScores.model_validate(_first_json_object(text))
            except Exception:
                pass
    return None


def score_pillars(
    *,
    facts: FactSnapshot,
    analyst_reports: Dict[str, str],
    llm: Any,
) -> PillarScores:
    """Returns parsed PillarScores. Raises PillarScoringError on any failure."""
    messages = _build_prompt(facts, analyst_reports)
    try:
        structured = llm.with_structured_output(PillarScores)
        result = structured.invoke(messages)
    except Exception as exc:
        raise PillarScoringError(f"Pillar scoring failed: {exc}") from exc

    coerced = _pillar_scores_from_invoke_result(result)
    if coerced is not None:
        return coerced

    logger.warning(
        "Pillar structured output returned %s; retrying via plain llm.invoke + JSON parse",
        type(result).__name__,
    )
    try:
        raw = llm.invoke(_messages_with_json_fallback_hint(messages))
        coerced = _pillar_scores_from_invoke_result(raw)
        if coerced is not None:
            return coerced
        text = _block_content_to_text(getattr(raw, "content", raw)).strip()
        if not text:
            raise ValueError("empty content from llm.invoke")
        return PillarScores.model_validate(_first_json_object(text))
    except Exception as exc:
        raise PillarScoringError(
            f"Unexpected scoring result type: {type(result).__name__}"
        ) from exc
