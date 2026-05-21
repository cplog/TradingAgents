"""LangGraph node: build standardized dimensions after analysts, before research debate."""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict

from tradingagents.agents.utils.dimensions_summary import render_compact_dimensions_summary

logger = logging.getLogger(__name__)


def create_dimensions_snapshot_node(
    quick_llm: Any,
    config: Dict[str, Any],
) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """Return a node that populates dimensions_summary / dimensions_snapshot_json on state."""

    def dimensions_snapshot_node(state: Dict[str, Any]) -> Dict[str, Any]:
        cfg = config or {}
        if not bool(cfg.get("dimensions_enabled", True)):
            return {
                "dimensions_summary": "",
                "dimensions_error": "",
                "dimensions_snapshot_json": "",
            }
        if not bool(cfg.get("dimensions_in_graph", True)):
            return {
                "dimensions_summary": "",
                "dimensions_error": "",
                "dimensions_snapshot_json": "",
            }

        try:
            from api.dimensions.builder import DimensionsBuildError, build_dimensions
        except ImportError as exc:
            msg = f"api.dimensions not importable: {exc}"
            logger.warning(msg)
            return {
                "dimensions_summary": "",
                "dimensions_error": msg,
                "dimensions_snapshot_json": "",
            }

        ticker = str(state.get("company_of_interest") or "").strip()
        trade_date = str(state.get("trade_date") or "").strip()
        if not ticker or not trade_date:
            return {
                "dimensions_summary": "",
                "dimensions_error": "missing company_of_interest or trade_date",
                "dimensions_snapshot_json": "",
            }

        analyst_reports = {
            "market": state.get("market_report") or "",
            "social": state.get("sentiment_report") or "",
            "news": state.get("news_report") or "",
            "fundamentals": state.get("fundamentals_report") or "",
            "hot_money": state.get("hot_money_report") or "",
            "policy": state.get("policy_report") or "",
            "lockup": state.get("lockup_report") or "",
            "kronos": state.get("kronos_report") or "",
        }

        try:
            from api.llm_clients import adapt_for_structured_output

            provider = str(cfg.get("llm_provider") or "openai")
            llm = adapt_for_structured_output(quick_llm, provider)
            dimensions = build_dimensions(
                ticker=ticker,
                as_of_date=trade_date,
                analyst_reports=analyst_reports,
                llm=llm,
                config=cfg,
            )
            payload = dimensions.model_dump()
            summary = render_compact_dimensions_summary(payload)
            return {
                "dimensions_summary": summary,
                "dimensions_error": "",
                "dimensions_snapshot_json": json.dumps(payload, ensure_ascii=False),
            }
        except DimensionsBuildError as exc:
            logger.warning("Dimensions snapshot skipped: %s", exc)
            return {
                "dimensions_summary": "",
                "dimensions_error": str(exc),
                "dimensions_snapshot_json": "",
            }
        except Exception as exc:
            logger.exception("Unexpected dimensions snapshot failure")
            return {
                "dimensions_summary": "",
                "dimensions_error": f"{type(exc).__name__}: {exc}",
                "dimensions_snapshot_json": "",
            }

    return dimensions_snapshot_node
