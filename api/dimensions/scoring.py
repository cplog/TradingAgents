"""Pillar scoring: single-call (legacy) and robust separate-call modes."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from api.dimensions.schemas import (
    FactSnapshot,
    FundamentalsPillar,
    MarketPillar,
    NewsPillar,
    PillarScore,
    PillarScores,
    SentimentPillar,
)

logger = logging.getLogger(__name__)


class PillarScoringError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Legacy single-call scoring (kept for backward compatibility / tests)
# ---------------------------------------------------------------------------

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


def _build_prompt(facts: FactSnapshot, reports: Dict[str, str], *, peer_scope: Optional[str] = None, data_quality_flags: Optional[List[str]] = None) -> list[dict]:
    facts_json = json.dumps(facts.model_dump(), default=str, indent=2)
    body = [f"## Facts\n```json\n{facts_json}\n```"]
    for key in ("market", "social", "news", "fundamentals"):
        text = reports.get(key) or "(no report available)"
        body.append(f"## {key.title()} Analyst Report\n{text}")
    for key, title in _SUPPLEMENTARY_REPORT_KEYS:
        text = (reports.get(key) or "").strip()
        if text:
            body.append(f"## {title} Analyst Report (supplementary)\n{text}")

    # Inject known data blind spots so the LLM does not hallucinate confidence
    # where facts are genuinely missing.
    caveats: List[str] = []
    if data_quality_flags:
        for flag in data_quality_flags:
            if flag.startswith("missing_"):
                caveats.append(flag)
    if peer_scope == "unavailable":
        caveats.append("peer_universe_unavailable — no peer-relative calibration possible")
    if caveats:
        body.append(
            "## Data Caveats\n"
            "The following metrics are missing or synthetic; score conservatively "
            "(avoid extreme 1 or 5 scores) when they affect a dimension:\n"
            + "\n".join(f"- {c}" for c in caveats)
        )

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
    peer_scope: Optional[str] = None,
    data_quality_flags: Optional[List[str]] = None,
) -> PillarScores:
    """Returns parsed PillarScores. Raises PillarScoringError on any failure."""
    messages = _build_prompt(facts, analyst_reports, peer_scope=peer_scope, data_quality_flags=data_quality_flags)
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
    raw_text_for_log: str = ""
    try:
        raw = llm.invoke(_messages_with_json_fallback_hint(messages))
        coerced = _pillar_scores_from_invoke_result(raw)
        if coerced is not None:
            return coerced
        text = _block_content_to_text(getattr(raw, "content", raw)).strip()
        raw_text_for_log = text
        if not text:
            raise ValueError("empty content from llm.invoke")
        return PillarScores.model_validate(_first_json_object(text))
    except Exception as exc:
        # Surface what the model actually emitted — the previous error message
        # ("Unexpected scoring result type: NoneType") buried the fallback
        # failure and made Ollama issues impossible to diagnose from the run
        # record. Truncate to keep flag strings manageable.
        snippet = raw_text_for_log[:500].replace("\n", " ")
        if raw_text_for_log:
            logger.warning(
                "Pillar scoring fallback output (truncated 500c): %s", snippet
            )
        raise PillarScoringError(
            f"Pillar scoring fallback failed after structured returned "
            f"{type(result).__name__}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Robust separate-call scoring (preferred for production)
# ---------------------------------------------------------------------------

_PILLAR_SCHEMAS: Dict[str, Tuple[type, str, Tuple[str, ...]]] = {
    "market": (
        MarketPillar,
        "Market & Technical Analysis",
        ("market", "kronos", "hot_money"),
    ),
    "sentiment": (
        SentimentPillar,
        "Sentiment & Social Analysis",
        ("social", "hot_money"),
    ),
    "news": (
        NewsPillar,
        "News & Catalyst Analysis",
        ("news", "policy", "hot_money"),
    ),
    "fundamentals": (
        FundamentalsPillar,
        "Fundamental Analysis",
        ("fundamentals", "lockup", "policy"),
    ),
}


def _neutral_pillar_score() -> PillarScore:
    return PillarScore(score=3, rationale="neutral default (pillar scoring unavailable)")


def _neutral_market_pillar() -> MarketPillar:
    n = _neutral_pillar_score()
    return MarketPillar(
        trend=n,
        momentum=n,
        volatility_risk=n,
        setup_quality=n,
    )


def _neutral_sentiment_pillar() -> SentimentPillar:
    n = _neutral_pillar_score()
    return SentimentPillar(
        retail_sentiment=n,
        social_buzz=n,
        consensus_quality=n,
        narrative_strength=n,
    )


def _neutral_news_pillar() -> NewsPillar:
    n = _neutral_pillar_score()
    return NewsPillar(
        catalyst_strength=n,
        macro_alignment=n,
        headline_quality=n,
        surprise_risk=n,
    )


def _neutral_fundamentals_pillar() -> FundamentalsPillar:
    n = _neutral_pillar_score()
    return FundamentalsPillar(
        valuation=n,
        growth=n,
        profitability=n,
        balance_sheet_strength=n,
    )


def _build_pillar_prompt(
    pillar_name: str,
    facts: FactSnapshot,
    analyst_reports: Dict[str, str],
    peer_scope: Optional[str] = None,
    data_quality_flags: Optional[List[str]] = None,
) -> list[dict]:
    """Build a focused prompt for a single pillar."""
    schema_cls, title, report_keys = _PILLAR_SCHEMAS[pillar_name]

    facts_json = json.dumps(facts.model_dump(), default=str, indent=2)
    body = [f"## Facts\n```json\n{facts_json}\n```"]

    for key in report_keys:
        text = analyst_reports.get(key) or ""
        if text.strip():
            body.append(f"## {key.title()} Analyst Report\n{text}")

    if not any((analyst_reports.get(k) or "").strip() for k in report_keys):
        body.append("## Analyst Reports\n(no relevant reports available for this pillar)")

    caveats: List[str] = []
    if data_quality_flags:
        for flag in data_quality_flags:
            if flag.startswith("missing_"):
                caveats.append(flag)
    if peer_scope == "unavailable":
        caveats.append("peer_universe_unavailable — no peer-relative calibration possible")
    if caveats:
        body.append(
            "## Data Caveats\n"
            "The following metrics are missing or synthetic; score conservatively "
            "(avoid extreme 1 or 5 scores) when they affect a dimension:\n"
            + "\n".join(f"- {c}" for c in caveats)
        )

    system = (
        f"You are a quantitative research analyst focused on {title}.\n\n"
        "Score the following sub-dimensions on a 1-5 scale with a one-sentence "
        "rationale per score. Be calibrated: 3 = average; 5 is reserved for genuinely "
        "standout cases. 1 indicates serious concern.\n\n"
    )
    if pillar_name in ("market", "news"):
        system += (
            "CRITICAL: `volatility_risk` and `surprise_risk` are inverted — "
            "HIGHER score means LOWER risk.\n"
        )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(body)},
    ]


def _parse_single_pillar(
    pillar_name: str,
    result: Any,
) -> Optional[Any]:
    """Best-effort parse of a single pillar from an LLM result."""
    schema_cls, _title, _report_keys = _PILLAR_SCHEMAS[pillar_name]

    if isinstance(result, schema_cls):
        return result

    parsed = getattr(result, "parsed", None)
    if isinstance(parsed, schema_cls):
        return parsed
    if isinstance(parsed, dict):
        try:
            return schema_cls.model_validate(parsed)
        except Exception:
            pass

    if isinstance(result, dict):
        try:
            return schema_cls.model_validate(result)
        except Exception:
            pass

    content = getattr(result, "content", None)
    if content is not None:
        text = _block_content_to_text(content).strip()
        if text:
            try:
                return schema_cls.model_validate(_first_json_object(text))
            except Exception:
                pass

    return None


def score_pillars_separate(
    *,
    facts: FactSnapshot,
    analyst_reports: Dict[str, str],
    llm: Any,
    peer_scope: Optional[str] = None,
    data_quality_flags: Optional[List[str]] = None,
) -> Tuple[PillarScores, List[str]]:
    """Score each pillar in a separate LLM call.

    Returns:
        (PillarScores, list of warning flags).  If a single pillar fails, it
        defaults to neutral (3/5) while the other three retain their scored
        values.  This prevents one malformed response from destroying the
        entire dimensions snapshot.
    """
    flags: List[str] = []
    pillars: Dict[str, Any] = {}

    for pillar_name in ("market", "sentiment", "news", "fundamentals"):
        schema_cls, title, _report_keys = _PILLAR_SCHEMAS[pillar_name]
        messages = _build_pillar_prompt(
            pillar_name,
            facts,
            analyst_reports,
            peer_scope=peer_scope,
            data_quality_flags=data_quality_flags,
        )

        try:
            structured = llm.with_structured_output(schema_cls)
            result = structured.invoke(messages)
        except Exception as exc:
            logger.warning(
                "Pillar %s structured invoke failed: %s", pillar_name, exc
            )
            result = None

        parsed = _parse_single_pillar(pillar_name, result) if result is not None else None

        if parsed is None and result is not None:
            # Try JSON fallback
            try:
                raw = llm.invoke(messages)
                parsed = _parse_single_pillar(pillar_name, raw)
            except Exception as exc2:
                logger.warning(
                    "Pillar %s fallback invoke failed: %s", pillar_name, exc2
                )

        if parsed is not None:
            pillars[pillar_name] = parsed
            logger.info("Pillar %s scored successfully", pillar_name)
        else:
            flags.append(f"pillar_{pillar_name}_scoring_failed")
            if pillar_name == "market":
                pillars[pillar_name] = _neutral_market_pillar()
            elif pillar_name == "sentiment":
                pillars[pillar_name] = _neutral_sentiment_pillar()
            elif pillar_name == "news":
                pillars[pillar_name] = _neutral_news_pillar()
            elif pillar_name == "fundamentals":
                pillars[pillar_name] = _neutral_fundamentals_pillar()
            logger.warning(
                "Pillar %s defaulted to neutral (3/5) after scoring failure", pillar_name
            )

    return (
        PillarScores(
            market=pillars["market"],
            sentiment=pillars["sentiment"],
            news=pillars["news"],
            fundamentals=pillars["fundamentals"],
        ),
        flags,
    )
