"""Report builder for the API.

Reuses the on-disk report layout from the CLI, but adds JSON/structured
serialization and optional Jinja2 post-processing.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from api.tickers import _safe_ticker_component

# Analyst id → (state dict key, reports dict key)
_ANALYST_FIELDS: Tuple[Tuple[str, str, str], ...] = (
    ("market", "market_report", "market"),
    ("social", "sentiment_report", "social"),
    ("news", "news_report", "news"),
    ("fundamentals", "fundamentals_report", "fundamentals"),
    ("hot_money", "hot_money_report", "hot_money"),
    ("policy", "policy_report", "policy"),
    ("lockup", "lockup_report", "lockup"),
    ("kronos", "kronos_report", "kronos"),
)

_ANALYST_BY_ID: Dict[str, Tuple[str, str]] = {
    aid: (state_key, section_key) for aid, state_key, section_key in _ANALYST_FIELDS
}

_EMPTY_ANALYST_DETAIL = (
    "No markdown report was stored after this analyst step. Common causes: "
    "(1) the model's **last turn still had pending tool calls** — several analysts only save "
    "text when the LLM returns plain content with no tools; "
    "(2) provider timeout or rate limit; "
    "(3) structured-output fallback returned empty text."
)

# kronos_status values (mirrors api.kronos.schema.KronosStatus) → user-facing detail.
# When the LLM "kronos" analyst node has been replaced by api.jobs._propagate_sync
# (real Kronos forecast pre-warmed before graph entry), an empty kronos_report
# never means "the LLM left a pending tool call" — it always reflects a Kronos
# pipeline outcome. Surface that instead of the generic detail.
_KRONOS_STATUS_DETAILS: Dict[str, str] = {
    "disabled": (
        "Kronos is disabled in this environment (KRONOS_ENABLED=false)."
    ),
    "insufficient_data": (
        "Not enough OHLCV history to run the Kronos forecast for this ticker/date "
        "(need KRONOS_LOOKBACK bars)."
    ),
    "load_failed": (
        "Kronos model could not be loaded. Likely causes: `torch` not installed "
        "in this environment, vendor/kronos missing, or HuggingFace weights "
        "unreachable. Run scripts/dev_up.sh to set up the model."
    ),
    "predict_failed": (
        "Kronos model loaded but prediction failed at runtime. See server logs "
        "(`api.jobs` / `api.kronos`) for the underlying exception."
    ),
    "timeout": (
        "Kronos forecast exceeded its timeout (KRONOS_TIMEOUT_SECONDS)."
    ),
}


def _analyst_label(analyst_id: str) -> str:
    return analyst_id.replace("_", " ").strip().title()


def _empty_detail_for(analyst_id: str, final_state: Dict[str, Any]) -> str:
    """Return the most-informative empty-report explanation for an analyst.

    Kronos has a typed status field (``final_state["kronos_status"]``) populated
    by api.jobs._propagate_sync; prefer it over the generic detail.
    """
    if analyst_id == "kronos":
        status = str(final_state.get("kronos_status") or "").strip().lower()
        specific = _KRONOS_STATUS_DETAILS.get(status)
        if specific:
            return specific
    return _EMPTY_ANALYST_DETAIL


def build_analyst_coverage(
    selected_analysts: List[str], final_state: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """Per selected analyst: ok vs empty, for API/UI diagnostics."""
    out: Dict[str, Dict[str, Any]] = {}
    for analyst_id in selected_analysts:
        pair = _ANALYST_BY_ID.get(analyst_id)
        if not pair:
            out[analyst_id] = {
                "status": "unknown_id",
                "section_key": analyst_id,
                "detail": "Not a registered analyst id in this build.",
            }
            continue
        state_key, section_key = pair
        raw = final_state.get(state_key)
        text = (raw if isinstance(raw, str) else "") or ""
        stripped = text.strip()
        if stripped:
            out[analyst_id] = {
                "status": "ok",
                "section_key": section_key,
                "chars": len(stripped),
            }
        else:
            entry: Dict[str, Any] = {
                "status": "empty",
                "section_key": section_key,
                "detail": _empty_detail_for(analyst_id, final_state),
            }
            if analyst_id == "kronos":
                k_status = str(final_state.get("kronos_status") or "").strip().lower()
                if k_status:
                    entry["kronos_status"] = k_status
            out[analyst_id] = entry
    return out


def _empty_analyst_body(
    analyst_id: str, state_key: str, final_state: Dict[str, Any]
) -> str:
    label = _analyst_label(analyst_id)
    return (
        f"**Status:** empty — no report text was captured for the **{label}** analyst.\n\n"
        f"{_empty_detail_for(analyst_id, final_state)}\n\n"
        f"_Internal report field:_ `{state_key}`"
    )


def rating_to_confidence(rating: str) -> float:
    """Map PM rating text to a rough confidence score for batch tables."""
    r = (rating or "").strip().lower()
    tiers = {
        "buy": 0.92,
        "overweight": 0.78,
        "hold": 0.55,
        "underweight": 0.35,
        "sell": 0.18,
    }
    for word, score in tiers.items():
        if word in r:
            return score
    return 0.5


# Direction of factors when paired with a bullish (long) call.
# +1 = supports bullish, -1 = a bullish call expects the inverse, 0 = neutral.
_FACTOR_BULL_DIRECTION = {
    "value": 1,
    "growth": 1,
    "quality": 1,
    "momentum": 1,
    "low_risk": 1,
    "sentiment": 1,
}


def _rating_direction(rating: str) -> int:
    """+1 bullish (Buy/Overweight), -1 bearish (Underweight/Sell), 0 neutral (Hold)."""
    r = (rating or "").strip().lower()
    if "buy" in r or "overweight" in r:
        return 1
    if "sell" in r or "underweight" in r:
        return -1
    return 0


def calibrate_confidence(
    rating: str,
    factor_scores: Optional[Dict[str, Any]] = None,
    data_quality_flags: Optional[List[str]] = None,
    conflicting_dimensions: Optional[List[str]] = None,
    peer_scope: Optional[str] = None,
) -> Dict[str, Any]:
    """Produce a calibrated confidence score with auditable inputs.

    Returns: {
      raw_tier: float,            # original rating-tier confidence (0..1)
      score: float,               # calibrated 0..1
      breakdown: {tier, coherence_penalty, data_quality_penalty, peer_penalty},
      inputs: {
        supporting_factors: [{key, score}],
        conflicting_factors: [{key, score}],
        weak_data: [str],         # data_quality_flags that reduced score
        peer_scope: str|None,
      }
    }
    """
    base = rating_to_confidence(rating)
    direction = _rating_direction(rating)
    flags = list(data_quality_flags or [])

    supporting: List[Dict[str, Any]] = []
    conflicting: List[Dict[str, Any]] = []

    if factor_scores and direction != 0:
        for key, dirn in _FACTOR_BULL_DIRECTION.items():
            entry = factor_scores.get(key) if isinstance(factor_scores, dict) else None
            score = None
            if isinstance(entry, dict):
                score = entry.get("score")
            elif isinstance(entry, (int, float)):
                score = float(entry)
            if score is None:
                continue
            # Align direction with rating: bull call wants high factor; bear call wants low.
            adjusted = score if direction == 1 else (100 - score)
            row = {"key": key, "score": float(score)}
            if adjusted >= 60:
                supporting.append(row)
            elif adjusted <= 40:
                conflicting.append(row)

    # Factor-coherence penalty: 8 pts per conflicting factor, capped at 25.
    coherence_penalty = min(0.25, 0.08 * len(conflicting))

    # Data-quality penalty: 4 pts per flag, capped at 20.
    data_quality_penalty = min(0.20, 0.04 * len(flags))

    # Peer-scope penalty for thin peer comparability.
    peer_penalty = 0.0
    if peer_scope in ("unavailable", None):
        peer_penalty = 0.10
    elif peer_scope == "global_fallback":
        peer_penalty = 0.05

    score = max(0.0, base - coherence_penalty - data_quality_penalty - peer_penalty)

    return {
        "raw_tier": round(base, 3),
        "score": round(score, 3),
        "breakdown": {
            "tier": round(base, 3),
            "coherence_penalty": round(coherence_penalty, 3),
            "data_quality_penalty": round(data_quality_penalty, 3),
            "peer_penalty": round(peer_penalty, 3),
        },
        "inputs": {
            "supporting_factors": supporting,
            "conflicting_factors": conflicting,
            "weak_data": flags,
            "peer_scope": peer_scope,
        },
    }


def build_result(
    final_state: Dict[str, Any],
    rating: str,
    ticker: str,
    date: str,
    config: Dict[str, Any],
    selected_analysts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build the API result payload and write artifacts to disk."""

    snap_raw = (final_state.get("dimensions_snapshot_json") or "").strip()
    dimensions_in_graph = bool(snap_raw)

    reports: Dict[str, str] = {}
    analyst_coverage: Optional[Dict[str, Dict[str, Any]]] = None

    if selected_analysts:
        analyst_coverage = build_analyst_coverage(selected_analysts, final_state)
        for analyst_id in selected_analysts:
            pair = _ANALYST_BY_ID.get(analyst_id)
            if not pair:
                continue
            state_key, section_key = pair
            raw = final_state.get(state_key)
            text = (raw if isinstance(raw, str) else "") or ""
            if text.strip():
                reports[section_key] = text
            else:
                reports[section_key] = _empty_analyst_body(
                    analyst_id, state_key, final_state
                )
    else:
        # Back-compat: omit empty analyst sections (callers without selection info).
        if final_state.get("market_report"):
            reports["market"] = final_state["market_report"]
        if final_state.get("sentiment_report"):
            reports["social"] = final_state["sentiment_report"]
        if final_state.get("news_report"):
            reports["news"] = final_state["news_report"]
        if final_state.get("fundamentals_report"):
            reports["fundamentals"] = final_state["fundamentals_report"]
        if final_state.get("hot_money_report"):
            reports["hot_money"] = final_state["hot_money_report"]
        if final_state.get("policy_report"):
            reports["policy"] = final_state["policy_report"]
        if final_state.get("lockup_report"):
            reports["lockup"] = final_state["lockup_report"]
        if final_state.get("kronos_report"):
            reports["kronos"] = final_state["kronos_report"]

    if final_state.get("investment_plan"):
        reports["research_plan"] = final_state["investment_plan"]
    if final_state.get("trader_investment_plan"):
        reports["trader_plan"] = final_state["trader_investment_plan"]
    if final_state.get("final_trade_decision"):
        reports["portfolio_decision"] = final_state["final_trade_decision"]

    # Structured fields (if present in state from structured-output agents)
    structured: Dict[str, Any] = {}
    debate = final_state.get("investment_debate_state", {})
    risk = final_state.get("risk_debate_state", {})
    if debate.get("judge_decision"):
        structured["research_manager_decision"] = debate["judge_decision"]
    if final_state.get("trader_investment_plan"):
        structured["trader_proposal"] = final_state["trader_investment_plan"]
    if risk.get("judge_decision"):
        structured["portfolio_manager_decision"] = risk["judge_decision"]

    # Write markdown artifact to disk
    results_dir = Path(config.get("results_dir", "./results"))
    safe_ticker = _safe_ticker_component(ticker)
    report_dir = results_dir / safe_ticker / date / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = _write_markdown_artifact(report_dir, final_state, ticker, date)

    payload: Dict[str, Any] = {
        "ticker": ticker,
        "date": date,
        "rating": rating,
        "confidence": rating_to_confidence(rating),
        "reports": reports,
        "structured": structured if structured else None,
        "artifacts_path": str(artifact_path),
        "completed_at": datetime.utcnow().isoformat() + "Z",
        "dimensions_in_graph": dimensions_in_graph,
    }
    if analyst_coverage is not None:
        payload["analyst_coverage"] = analyst_coverage

    from tradingagents.agents.utils.execution_context import (
        build_run_execution_annotation,
        derive_plan_levels,
        parse_run_snapshot_json,
    )

    run_snap = parse_run_snapshot_json(final_state.get("live_quote_at_run_json"))
    ref_price: Optional[float] = None
    if isinstance(run_snap, dict):
        q = run_snap.get("quote") or {}
        raw_px = q.get("price")
        if raw_px is not None:
            try:
                ref_price = float(raw_px)
            except (TypeError, ValueError):
                ref_price = None
    structured_payload = structured if structured else None
    plan_levels = derive_plan_levels(
        reports,
        structured=structured_payload,
        reference_price=ref_price,
    )
    payload["plan_levels"] = plan_levels
    annotation = build_run_execution_annotation(
        reports,
        run_snap,
        payload["completed_at"],
        structured=structured_payload,
        plan_levels=plan_levels,
    )
    if annotation:
        payload["live_context_at_run"] = annotation

    return payload


def _write_markdown_artifact(
    save_path: Path,
    final_state: Dict[str, Any],
    ticker: str,
    date: str,
) -> Path:
    """Write the same multi-section markdown report the CLI produces."""
    sections = []

    # 1. Analysts
    analyst_parts = []
    if final_state.get("market_report"):
        analyst_parts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        analyst_parts.append(("Social Analyst", final_state["sentiment_report"]))
    if final_state.get("news_report"):
        analyst_parts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("fundamentals_report"):
        analyst_parts.append(("Fundamentals Analyst", final_state["fundamentals_report"]))
    if final_state.get("hot_money_report"):
        analyst_parts.append(("Hot Money Analyst", final_state["hot_money_report"]))
    if final_state.get("policy_report"):
        analyst_parts.append(("Policy Analyst", final_state["policy_report"]))
    if final_state.get("lockup_report"):
        analyst_parts.append(("Lockup Analyst", final_state["lockup_report"]))
    if final_state.get("kronos_report"):
        analyst_parts.append(("Kronos Scenario Analyst", final_state["kronos_report"]))
    if analyst_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in analyst_parts)
        sections.append(f"## I. Analyst Team Reports\n\n{content}")

    if (final_state.get("dimensions_summary") or "").strip():
        sections.append(
            "## Standardized dimensions snapshot\n\n"
            "_Generated after analysts, before the research debate "
            "(same snapshot fed to Trader and Portfolio Manager)._ \n\n"
            f"{final_state['dimensions_summary']}"
        )
    elif (final_state.get("dimensions_error") or "").strip():
        sections.append(
            "## Standardized dimensions snapshot\n\n"
            f"_Build failed:_ {final_state['dimensions_error']}"
        )

    # 2. Research
    debate = final_state.get("investment_debate_state", {})
    research_parts = []
    if debate.get("bull_history"):
        research_parts.append(("Bull Researcher", debate["bull_history"]))
    if debate.get("bear_history"):
        research_parts.append(("Bear Researcher", debate["bear_history"]))
    if debate.get("judge_decision"):
        research_parts.append(("Research Manager", debate["judge_decision"]))
    if research_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in research_parts)
        sections.append(f"## II. Research Team Decision\n\n{content}")

    # 3. Trading
    if final_state.get("trader_investment_plan"):
        sections.append(
            f"## III. Trading Team Plan\n\n### Trader\n{final_state['trader_investment_plan']}"
        )

    # 4. Risk + 5. Portfolio
    risk = final_state.get("risk_debate_state", {})
    risk_parts = []
    if risk.get("aggressive_history"):
        risk_parts.append(("Aggressive Analyst", risk["aggressive_history"]))
    if risk.get("conservative_history"):
        risk_parts.append(("Conservative Analyst", risk["conservative_history"]))
    if risk.get("neutral_history"):
        risk_parts.append(("Neutral Analyst", risk["neutral_history"]))
    if risk_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in risk_parts)
        sections.append(f"## IV. Risk Management Team Decision\n\n{content}")
    if risk.get("judge_decision"):
        sections.append(
            f"## V. Portfolio Manager Decision\n\n### Portfolio Manager\n{risk['judge_decision']}"
        )

    header = f"# Trading Analysis Report: {ticker}\n\nDate: {date}\nGenerated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
    report_path = save_path / "complete_report.md"
    report_path.write_text(header + "\n\n".join(sections), encoding="utf-8")
    return report_path
