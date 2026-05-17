"""W1 dimensions-grounded commentary on the PM decision (1 LLM call)."""
from __future__ import annotations

import json
import logging
from typing import Any

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
    try:
        structured = llm.with_structured_output(DimensionsCommentary)
        result = structured.invoke(messages)
    except Exception as exc:
        raise CommentaryError(f"Commentary generation failed: {exc}") from exc
    if not isinstance(result, DimensionsCommentary):
        logger.warning(
            "Dimensions commentary structured output returned %s for ticker=%s as_of_date=%s "
            "(expected DimensionsCommentary; often means the LLM/json parser returned empty or invalid output)",
            type(result).__name__,
            dimensions.ticker,
            dimensions.as_of_date,
        )
        raise CommentaryError(f"Unexpected commentary type: {type(result).__name__}")
    return result
