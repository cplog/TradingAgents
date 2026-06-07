"""Options Strategist: translates the Portfolio Manager's equity decision into a
concrete options strategy using live options chain data.

Runs after the Portfolio Manager and before END. Produces an
OptionsRecommendation rendered back to markdown for display and storage.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional

from tradingagents.agents.schemas import OptionsRecommendation, render_options_recommendation
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.dataflows.options_data import (
    get_options_chain,
    get_options_context,
    get_options_expirations,
)

logger = logging.getLogger(__name__)


def _pick_expiration(expirations: List[str], min_dte: int = 21) -> Optional[str]:
    """Pick the nearest expiration that is at least ``min_dte`` days away.

    ``expirations`` are YYYY-MM-DD strings sorted by yfinance (ascending).
    """
    today = datetime.date.today()
    for exp in expirations:
        try:
            exp_date = datetime.date.fromisoformat(exp)
            dte = (exp_date - today).days
            if dte >= min_dte:
                return exp
        except ValueError:
            continue
    # Fallback: last expiration if none meet the min_dte
    return expirations[-1] if expirations else None


def _atm_slice(chain: Dict[str, Any], n: int = 10) -> Dict[str, Any]:
    """Return the ``n`` strikes closest to the underlying price."""
    underlying = chain.get("underlying_price")
    if underlying is None:
        return chain

    def _dist(strike: Any) -> float:
        try:
            return abs(float(strike) - float(underlying))
        except (TypeError, ValueError):
            return float("inf")

    calls = sorted(
        (c for c in chain.get("calls", []) if c.get("strike") is not None),
        key=lambda c: _dist(c["strike"]),
    )[:n]
    puts = sorted(
        (p for p in chain.get("puts", []) if p.get("strike") is not None),
        key=lambda p: _dist(p["strike"]),
    )[:n]

    return {
        "expiration": chain.get("expiration"),
        "underlying_price": underlying,
        "calls": calls,
        "puts": puts,
    }


def _build_chain_markdown(chain: Dict[str, Any]) -> str:
    """Compact markdown table of the ATM option chain."""
    if not chain:
        return "*(No options chain data available)*"
    underlying = chain.get("underlying_price")
    exp = chain.get("expiration")
    lines = [
        f"**Underlying price**: {underlying}",
        f"**Expiration**: {exp}",
        "",
        "| Strike | Call Bid | Call Ask | Call IV | Call Vol | Put Bid | Put Ask | Put IV | Put Vol |",
        "|--------|----------|----------|---------|----------|---------|---------|--------|---------|",
    ]
    calls = {c["strike"]: c for c in chain.get("calls", []) if c.get("strike") is not None}
    puts = {p["strike"]: p for p in chain.get("puts", []) if p.get("strike") is not None}
    strikes = sorted(set(calls.keys()) | set(puts.keys()))
    for s in strikes:
        c = calls.get(s, {})
        p = puts.get(s, {})
        lines.append(
            f"| {s} | "
            f"{c.get('bid', '-')} | {c.get('ask', '-')} | {c.get('impliedVolatility', '-')} | {c.get('volume', '-')} | "
            f"{p.get('bid', '-')} | {p.get('ask', '-')} | {p.get('impliedVolatility', '-')} | {p.get('volume', '-')} |"
        )
    return "\n".join(lines)


def _build_market_context_markdown(ctx: Dict[str, Any]) -> str:
    """Render earnings, short interest, and dividend context."""
    lines: List[str] = []
    if ctx.get("earnings_date"):
        lines.append(f"- Earnings date: {ctx['earnings_date']}")
    if ctx.get("ex_dividend_date"):
        lines.append(f"- Ex-dividend date: {ctx['ex_dividend_date']}")
    if ctx.get("short_percent_float") is not None:
        lines.append(f"- Short % of float: {ctx['short_percent_float']:.2%}")
    if ctx.get("short_ratio") is not None:
        lines.append(f"- Short ratio: {ctx['short_ratio']}")
    return "\n".join(lines) if lines else ""


def _extract_vol_metrics_from_dimensions(dim_summary: str) -> str:
    """Best-effort extraction of volatility-relevant lines from dimensions markdown."""
    if not dim_summary:
        return ""
    lines = dim_summary.splitlines()
    out: List[str] = []
    for line in lines:
        lowered = line.lower()
        if any(k in lowered for k in ("volatility", "realized_vol", "rsi", "beta", "low_risk")):
            out.append(line.strip())
    return "\n".join(out) if out else ""


def create_options_strategist(llm, config: Optional[Dict[str, Any]] = None):
    """Factory returning an Options Strategist LangGraph node."""
    structured_llm = bind_structured(llm, OptionsRecommendation, "Options Strategist")

    def options_strategist_node(state) -> dict:
        ticker = state.get("company_of_interest", "")
        instrument_context = get_instrument_context_from_state(state)
        pm_decision = state.get("final_trade_decision") or ""
        trader_plan = state.get("trader_investment_plan") or ""
        execution_context = (state.get("execution_context") or "").strip()
        dim_summary = (state.get("dimensions_summary") or "").strip()
        dim_err = (state.get("dimensions_error") or "").strip()

        # Fetch options data
        expirations = get_options_expirations(ticker)
        expiration = _pick_expiration(expirations)
        chain_raw: Dict[str, Any] = {}
        chain_md = "*(No options data available)*"
        if expiration:
            chain_raw = get_options_chain(ticker, expiration)
            if chain_raw.get("error"):
                chain_md = f"*(Options data error: {chain_raw['error']})*"
            else:
                chain_md = _build_chain_markdown(_atm_slice(chain_raw))
        else:
            chain_md = "*(No options expirations available for this ticker)*"

        market_ctx = get_options_context(ticker)
        market_ctx_md = _build_market_context_markdown(market_ctx)

        vol_block = _extract_vol_metrics_from_dimensions(dim_summary)
        dim_block = ""
        if vol_block:
            dim_block = (
                "\n\n**Volatility-relevant dimensions snapshot**:\n"
                f"{vol_block}\n"
            )
        elif dim_err:
            dim_block = f"\n\n**Dimensions snapshot:** unavailable ({dim_err}).\n"

        execution_note = f"\n\n{execution_context}\n" if execution_context else ""

        system_message = (
            "You are an options strategist. Given a final equity rating, price levels, "
            "and live options chain data, design a concrete options strategy that expresses "
            "the same directional view with defined risk.\n\n"
            "Strategy selection rules:\n"
            "- Buy / Overweight → bullish vertical spreads, long calls, or cash-secured puts.\n"
            "- Sell / Underweight → bearish vertical spreads, long puts, or covered calls.\n"
            "- Hold / neutral → iron condor, calendar spread, or no options position.\n"
            "- Compare implied volatility to 30-day realized volatility from the dimensions snapshot. "
            "If IV > realized vol, options are expensive → sell premium (credit spreads / iron condors). "
            "If IV < realized vol, options are cheap → buy premium (debit spreads / long options). "
            "Never call options 'expensive' when IV is below realized vol.\n"
            "- High IV in isolation (expensive options) → prefer credit spreads / iron condors (sell premium).\n"
            "- Low IV in isolation (cheap options) → prefer debit spreads / long options (buy premium).\n"
            "- If earnings fall before expiration, expect a volatility event. Avoid short gamma through earnings "
            "unless explicitly selling elevated IV with a plan to close before the event.\n"
            "- If short_percent_float > 0.10, explicitly mention it in the rationale and explain how it affects put skew or gamma squeeze risk. Do not silently ignore high short interest.\n"
            "- Anchor strike selection to the trader's entry/stop and the PM's price target.\n"
            "- Default to defined-risk strategies (spreads) unless the thesis strongly favors naked directional exposure.\n"
            "- If no suitable options chain is available, set strategy_name to 'No suitable options' and "
            "alternative to 'Use underlying equity only.'\n"
            + get_language_instruction()
        )

        user_message = (
            f"{instrument_context}\n\n"
            f"**Portfolio Manager Decision**:\n{pm_decision}\n\n"
            f"**Trader Proposal**:\n{trader_plan}\n"
            f"{dim_block}{execution_note}\n"
            f"**Live Options Chain** (nearest expiration ≥21 DTE):\n{chain_md}\n"
            f"{market_ctx_md}\n\n"
            "Design the options strategy now."
        )

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]

        recommendation_md = invoke_structured_or_freetext(
            structured_llm,
            llm,
            messages,
            render_options_recommendation,
            "Options Strategist",
        )

        return {
            "options_recommendation": recommendation_md,
            "options_chain_snapshot": chain_raw if chain_raw else None,
        }

    return options_strategist_node
