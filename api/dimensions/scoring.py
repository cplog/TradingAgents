"""Single structured-output LLM call producing PillarScores."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from api.dimensions.schemas import FactSnapshot, PillarScores

logger = logging.getLogger(__name__)


class PillarScoringError(RuntimeError):
    pass


_SYSTEM = """You are a quantitative research analyst. Given (a) a stock's deterministic facts
and (b) four analyst reports (Market, Sentiment, News, Fundamentals), score 16 sub-dimensions
on a 1-5 scale with a one-sentence rationale per score.

CRITICAL: `volatility_risk` and `surprise_risk` are inverted — HIGHER score means LOWER risk.
For all other dimensions, higher score means stronger/better.

Be calibrated. 3 = average; 5 is reserved for genuinely standout cases."""


def _build_prompt(facts: FactSnapshot, reports: Dict[str, str]) -> list[dict]:
    facts_json = json.dumps(facts.model_dump(), default=str, indent=2)
    body = [f"## Facts\n```json\n{facts_json}\n```"]
    for key in ("market", "social", "news", "fundamentals"):
        text = reports.get(key) or "(no report available)"
        body.append(f"## {key.title()} Analyst Report\n{text}")
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": "\n\n".join(body)},
    ]


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
    if not isinstance(result, PillarScores):
        raise PillarScoringError(f"Unexpected scoring result type: {type(result).__name__}")
    return result
