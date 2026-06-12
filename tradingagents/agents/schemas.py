"""Pydantic schemas used by agents that produce structured output.

The framework's primary artifact is still prose: each agent's natural-language
reasoning is what users read in the saved markdown reports and what the
downstream agents read as context.  Structured output is layered onto the
three decision-making agents (Research Manager, Trader, Portfolio Manager)
so that:

- Their outputs follow consistent section headers across runs and providers
- Each provider's native structured-output mode is used (json_schema for
  OpenAI/xAI, response_schema for Gemini, tool-use for Anthropic)
- Schema field descriptions become the model's output instructions, freeing
  the prompt body to focus on context and the rating-scale guidance
- A render helper turns the parsed Pydantic instance back into the same
  markdown shape the rest of the system already consumes, so display,
  memory log, and saved reports keep working unchanged
"""

from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared rating types
# ---------------------------------------------------------------------------


class PortfolioRating(str, Enum):
    """5-tier rating used by the Research Manager and Portfolio Manager."""

    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class TraderAction(str, Enum):
    """3-tier transaction direction used by the Trader.

    The Trader's job is to translate the Research Manager's investment plan
    into a concrete transaction proposal: should the desk execute a Buy, a
    Sell, or sit on Hold this round.  Position sizing and the nuanced
    Overweight / Underweight calls happen later at the Portfolio Manager.
    """

    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


# ---------------------------------------------------------------------------
# Research Manager
# ---------------------------------------------------------------------------


class ResearchPlan(BaseModel):
    """Structured investment plan produced by the Research Manager.

    Hand-off to the Trader: the recommendation pins the directional view,
    the rationale captures which side of the bull/bear debate carried the
    argument, and the strategic actions translate that into concrete
    instructions the trader can execute against.
    """

    recommendation: PortfolioRating = Field(
        description=(
            "The investment recommendation. Exactly one of Buy / Overweight / "
            "Hold / Underweight / Sell. Reserve Hold for situations where the "
            "evidence on both sides is genuinely balanced; otherwise commit to "
            "the side with the stronger arguments."
        ),
    )
    rationale: str = Field(
        description=(
            "Conversational summary of the key points from both sides of the "
            "debate, ending with which arguments led to the recommendation. "
            "Speak naturally, as if to a teammate."
        ),
    )
    strategic_actions: str = Field(
        description=(
            "Concrete steps for the trader to implement the recommendation, "
            "including position sizing guidance consistent with the rating."
        ),
    )


def render_research_plan(plan: ResearchPlan) -> str:
    """Render a ResearchPlan to markdown for storage and the trader's prompt context."""
    return "\n".join([
        f"**Recommendation**: {plan.recommendation.value}",
        "",
        f"**Rationale**: {plan.rationale}",
        "",
        f"**Strategic Actions**: {plan.strategic_actions}",
    ])


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------


class TraderProposal(BaseModel):
    """Structured transaction proposal produced by the Trader.

    The trader reads the Research Manager's investment plan and the analyst
    reports, then turns them into a concrete transaction: what action to
    take, the reasoning that justifies it, and the practical levels for
    entry, stop-loss, and sizing.
    """

    action: TraderAction = Field(
        description="The transaction direction. Exactly one of Buy / Hold / Sell.",
    )
    reasoning: str = Field(
        description=(
            "The case for this action, anchored in the analysts' reports and "
            "the research plan. Two to four sentences."
        ),
    )
    entry_price: Optional[float] = Field(
        default=None,
        description="Optional entry price target in the instrument's quote currency.",
    )
    stop_loss: Optional[float] = Field(
        default=None,
        description="Optional stop-loss price in the instrument's quote currency.",
    )
    position_sizing: Optional[str] = Field(
        default=None,
        description="Optional sizing guidance, e.g. '5% of portfolio'.",
    )


def render_trader_proposal(proposal: TraderProposal) -> str:
    """Render a TraderProposal to markdown.

    The trailing ``FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`` line is
    preserved for backward compatibility with the analyst stop-signal text
    and any external code that greps for it.
    """
    parts = [
        f"**Action**: {proposal.action.value}",
        "",
        f"**Reasoning**: {proposal.reasoning}",
    ]
    if proposal.entry_price is not None:
        parts.extend(["", f"**Entry Price**: {proposal.entry_price}"])
    if proposal.stop_loss is not None:
        parts.extend(["", f"**Stop Loss**: {proposal.stop_loss}"])
    if proposal.position_sizing:
        parts.extend(["", f"**Position Sizing**: {proposal.position_sizing}"])
    parts.extend([
        "",
        f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value.upper()}**",
    ])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Portfolio Manager
# ---------------------------------------------------------------------------


class PortfolioDecision(BaseModel):
    """Structured output produced by the Portfolio Manager.

    The model fills every field as part of its primary LLM call; no separate
    extraction pass is required. Field descriptions double as the model's
    output instructions, so the prompt body only needs to convey context and
    the rating-scale guidance.
    """

    rating: PortfolioRating = Field(
        description=(
            "The final position rating. Exactly one of Buy / Overweight / Hold / "
            "Underweight / Sell, picked based on the analysts' debate."
        ),
    )
    conviction_score: int = Field(
        default=0,
        description=(
            "How confident you are in this rating on a 0-100 scale. "
            "0-30 = very low conviction (evidence is thin or conflicting), "
            "31-50 = low conviction, 51-70 = moderate conviction, "
            "71-85 = high conviction, 86-100 = very high conviction. "
            "Be honest and calibrated: most decisions should fall in the "
            "51-85 range. Reserve 86+ for exceptionally clear setups."
        ),
    )
    executive_summary: str = Field(
        description=(
            "A concise action plan covering entry strategy, position sizing, "
            "key risk levels, and time horizon. Two to four sentences."
        ),
    )
    investment_thesis: str = Field(
        description=(
            "Detailed reasoning anchored in specific evidence from the analysts' "
            "debate. Include a brief evidence tally: list the key factors supporting "
            "your rating and the key factors against it, with their approximate weights. "
            "If prior lessons are referenced in the prompt context, "
            "incorporate them; otherwise rely solely on the current analysis."
        ),
    )
    price_target: Optional[float] = Field(
        default=None,
        description="Optional target price in the instrument's quote currency.",
    )
    time_horizon: Optional[str] = Field(
        default=None,
        description="Optional recommended holding period, e.g. '3-6 months'.",
    )


def render_pm_decision(decision: PortfolioDecision) -> str:
    """Render a PortfolioDecision back to the markdown shape the rest of the system expects.

    Memory log, CLI display, and saved report files all read this markdown,
    so the rendered output preserves the exact section headers (``**Rating**``,
    ``**Executive Summary**``, ``**Investment Thesis**``) that downstream
    parsers and the report writers already handle.
    """
    parts = [
        f"**Rating**: {decision.rating.value}",
    ]
    if decision.conviction_score > 0:
        parts.extend(["", f"**Conviction**: {decision.conviction_score}/100"])
    parts.extend([
        "",
        f"**Executive Summary**: {decision.executive_summary}",
        "",
        f"**Investment Thesis**: {decision.investment_thesis}",
    ])
    if decision.price_target is not None:
        parts.extend(["", f"**Price Target**: {decision.price_target}"])
    if decision.time_horizon:
        parts.extend(["", f"**Time Horizon**: {decision.time_horizon}"])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Options Strategist
# ---------------------------------------------------------------------------


class OptionsLeg(BaseModel):
    """One leg of a multi-leg options strategy."""

    side: Literal["buy", "sell"] = Field(
        ..., description="Whether to buy (debit) or sell (credit) this leg."
    )
    option_type: Literal["call", "put"] = Field(..., description="Call or put.")
    strike: float = Field(..., description="Strike price in the underlying's currency.")
    expiration_dte: int = Field(..., description="Days to expiration at recommendation time.")
    expiration_date: Optional[str] = Field(
        default=None, description="Expiration date as YYYY-MM-DD."
    )


class OptionsRecommendation(BaseModel):
    """Structured options strategy produced by the Options Strategist.

    The strategist reads the Portfolio Manager's directional rating, the Trader's
    entry/stop levels, and live options chain data (IV, volume, OI) to propose a
    concrete options implementation of the equity view.
    """

    strategy_name: str = Field(
        ..., description="Human-readable strategy name, e.g. 'Bull Call Spread'."
    )
    directional_bias: Literal["bullish", "bearish", "neutral", "volatility"] = Field(
        ..., description="Primary directional bias of the strategy."
    )
    underlying_action: str = Field(
        ..., description="What to do with the underlying, e.g. 'Buy at entry'."
    )
    legs: List[OptionsLeg] = Field(
        default_factory=list,
        description="Ordered legs. Single-leg strategies have one entry."
    )
    max_risk: Optional[str] = Field(
        default=None,
        description="Maximum loss, e.g. 'Limited to $2.00 debit per spread'."
    )
    max_reward: Optional[str] = Field(
        default=None,
        description="Maximum gain, e.g. 'Unlimited above $180'."
    )
    breakeven_at_expiry: Optional[str] = Field(
        default=None,
        description="Breakeven price at expiration, e.g. '$172.50'."
    )
    rationale: str = Field(
        ..., description="Two to four sentences tying the strategy to the PM rating, vol regime, and price levels."
    )
    alternative: Optional[str] = Field(
        default=None,
        description="Simpler fallback if the primary strategy is unsuitable, e.g. 'Use underlying equity only'."
    )
    iv_context: Optional[str] = Field(
        default=None,
        description="One sentence describing the implied volatility regime (cheap, expensive, average)."
    )


def render_options_recommendation(rec: OptionsRecommendation) -> str:
    """Render an OptionsRecommendation to markdown for storage and display."""
    parts = [
        f"**Strategy**: {rec.strategy_name}",
        "",
        f"**Directional Bias**: {rec.directional_bias.value if hasattr(rec.directional_bias, 'value') else rec.directional_bias}",
        f"**Underlying Action**: {rec.underlying_action}",
    ]

    if rec.iv_context:
        parts.extend(["", f"**IV Context**: {rec.iv_context}"])

    if rec.legs:
        parts.extend(["", "**Legs**:", ""])
        parts.append("| Leg | Side | Type | Strike | Expiration |")
        parts.append("|-----|------|------|--------|------------|")
        for i, leg in enumerate(rec.legs, start=1):
            exp = leg.expiration_date or f"{leg.expiration_dte} DTE"
            parts.append(
                f"| {i} | {leg.side} | {leg.option_type} | {leg.strike} | {exp} |"
            )

    if rec.max_risk:
        parts.extend(["", f"**Max Risk**: {rec.max_risk}"])
    if rec.max_reward:
        parts.extend(["", f"**Max Reward**: {rec.max_reward}"])
    if rec.breakeven_at_expiry:
        parts.extend(["", f"**Breakeven at Expiry**: {rec.breakeven_at_expiry}"])

    parts.extend(["", f"**Rationale**: {rec.rationale}"])

    if rec.alternative:
        parts.extend(["", f"**Alternative**: {rec.alternative}"])

    return "\n".join(parts)
