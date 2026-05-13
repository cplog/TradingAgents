"""Report builder for the API.

Reuses the on-disk report layout from the CLI, but adds JSON/structured
serialization and optional Jinja2 post-processing.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from api.tickers import _safe_ticker_component


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


def build_result(
    final_state: Dict[str, Any],
    rating: str,
    ticker: str,
    date: str,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the API result payload and write artifacts to disk."""

    # Extract individual report sections
    reports: Dict[str, str] = {}
    if final_state.get("market_report"):
        reports["market"] = final_state["market_report"]
    if final_state.get("sentiment_report"):
        reports["social"] = final_state["sentiment_report"]
    if final_state.get("news_report"):
        reports["news"] = final_state["news_report"]
    if final_state.get("fundamentals_report"):
        reports["fundamentals"] = final_state["fundamentals_report"]
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

    return {
        "ticker": ticker,
        "date": date,
        "rating": rating,
        "confidence": rating_to_confidence(rating),
        "reports": reports,
        "structured": structured if structured else None,
        "artifacts_path": str(artifact_path),
        "completed_at": datetime.utcnow().isoformat() + "Z",
    }


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
    if analyst_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in analyst_parts)
        sections.append(f"## I. Analyst Team Reports\n\n{content}")

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
