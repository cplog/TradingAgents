"""Debate scoring node: numerically score bull vs bear arguments before RM decides.

Produces a structured ``DebateScore`` that the Research Manager uses as a
tie-breaker when the bull/bear evidence appears balanced.  This prevents the
RM from defaulting to Hold simply because both sides wrote persuasive prose.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from tradingagents.agents.utils.agent_utils import get_language_instruction
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)

logger = logging.getLogger(__name__)


class DebateScore(BaseModel):
    """Structured output from the debate scorer."""

    bull_score: int = Field(
        ge=0,
        le=100,
        description="Aggregate strength of the bull case (0=none, 100=overwhelming).",
    )
    bear_score: int = Field(
        ge=0,
        le=100,
        description="Aggregate strength of the bear case (0=none, 100=overwhelming).",
    )
    winner: str = Field(
        description="Exactly one of: bull, bear, tie. 'tie' only when scores are within 5 points.",
    )
    margin: int = Field(
        ge=0,
        le=100,
        description="Absolute difference between bull_score and bear_score.",
    )
    decisive_factors: list[str] = Field(
        default_factory=list,
        description="List of 1-3 factor names that most strongly drove the winner (e.g. 'revenue_growth', 'technical_trend', 'valuation').",
    )
    rationale: str = Field(
        description="One sentence explaining why the winner scored higher.",
    )


def _render_debate_score(score: DebateScore) -> str:
    return (
        f"**Debate Score**: Bull {score.bull_score} – Bear {score.bear_score} "
        f"(winner: {score.winner}, margin: {score.margin})\n\n"
        f"**Decisive Factors**: {', '.join(score.decisive_factors)}\n\n"
        f"**Rationale**: {score.rationale}"
    )


def create_debate_scorer(llm: Any) -> Any:
    """Return a LangGraph node that scores the bull/bear debate."""
    structured_llm = bind_structured(llm, DebateScore, "Debate Scorer")

    def debate_scorer_node(state: Dict[str, Any]) -> Dict[str, Any]:
        history = state.get("investment_debate_state", {}).get("history", "")
        if not history or len(history) < 200:
            # No meaningful debate to score; skip
            return {"debate_score": None}

        prompt = f"""You are a quantitative debate judge.  Read the bull/bear debate below and score each side on a 0-100 scale.

**Scoring dimensions** (mentally weight each ~20%):
1. **Quantitative evidence** — How many hard numbers (revenue growth %, margin, FCF yield, P/E, RSI, volume, etc.) support the case?
2. **Catalyst proximity** — Does the case cite events within 30 days (earnings, Fed decision, product launch, geopolitical resolution)?
3. **Risk/reward asymmetry** — Is the upside/downside clearly quantified with entry/stop/target levels?
4. **Technical trend alignment** — Does the case align with or contradict the dominant price trend?
5. **Fundamental valuation support** — Is the valuation argument grounded in peer-relative or historical multiples?

**Rules:**
- Score each side independently; do NOT average them to 50.
- If one side has 3+ more quantitative data points, give it at least a 10-point edge.
- If the bull case cites a near-term catalyst and the bear case does not, add 10-15 points to bull.
- If the bear case shows the stock is below every moving average with distribution volume, add 10-15 points to bear.
- "tie" is ONLY allowed when scores differ by ≤5 points AND both sides have equally strong quantitative support.

**Debate History:**
{history}

Return ONLY the structured score.{get_language_instruction()}"""

        try:
            score = invoke_structured_or_freetext(
                structured_llm,
                llm,
                prompt,
                _render_debate_score,
                "Debate Scorer",
            )
            # Also render to markdown for downstream agents
            rendered = _render_debate_score(score)
            return {
                "debate_score": score,
                "debate_score_text": rendered,
            }
        except Exception as exc:
            logger.warning("Debate scoring failed: %s", exc)
            return {"debate_score": None, "debate_score_text": ""}

    return debate_scorer_node
