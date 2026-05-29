"""LLM extraction pipeline for topic ticker candidates."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from api.tickers import normalize_ticker
from api.topics_models import (
    ExtractionResult,
    TickerCandidate,
    TickerMarket,
    TopicArticle,
)

logger = logging.getLogger(__name__)

_SYSTEM = """You are a financial research assistant. Given web articles about an investment theme,
extract publicly traded stock tickers that are materially relevant to the theme.

Rules:
- Prefer US listings (NYSE/NASDAQ) unless the theme is region-specific.
- Include HK (.HK) or China ADR tickers only when clearly relevant.
- Assign confidence 0.0–1.0: 0.9+ only when the article explicitly names the company/ticker;
  0.5–0.8 for strong indirect relevance; below 0.5 for weak mentions.
- Deduplicate tickers; keep the highest-confidence entry.
- Write a concise theme_summary (2–4 sentences) synthesizing the narrative across articles.
- Return JSON matching the schema exactly."""


def _build_llm(service_config: Dict[str, Any]):
    from tradingagents.llm_clients import create_llm_client
    from api.llm_clients.structured_output import adapt_for_structured_output

    provider = service_config.get("llm_provider", "openai")
    client = create_llm_client(
        provider=provider,
        model=service_config.get("quick_think_llm"),
        base_url=service_config.get("backend_url"),
    )
    return adapt_for_structured_output(client.get_llm(), provider)


def _articles_to_prompt(articles: List[TopicArticle], query: str) -> str:
    lines = [f"Theme query: {query}", "", "Articles:"]
    for i, art in enumerate(articles[:12], start=1):
        lines.append(f"{i}. {art.title}")
        if art.snippet:
            lines.append(f"   {art.snippet[:500]}")
        if art.url:
            lines.append(f"   URL: {art.url}")
    return "\n".join(lines)


def _first_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("no JSON object in LLM response")
    return json.loads(match.group(0))


def _infer_market(ticker: str) -> TickerMarket:
    if ticker.endswith(".HK"):
        return TickerMarket.hk
    if ticker.endswith(".SS") or ticker.endswith(".SZ"):
        return TickerMarket.cn
    return TickerMarket.us


def calibrate_confidence(raw: float) -> float:
    """Map raw LLM confidence to a conservative calibrated score."""
    if raw >= 0.95:
        return min(1.0, 0.85 + (raw - 0.95) * 1.5)
    if raw >= 0.8:
        return 0.65 + (raw - 0.8) * 1.0
    if raw >= 0.5:
        return 0.35 + (raw - 0.5) * 1.0
    return max(0.05, raw * 0.7)


def normalize_candidates(candidates: List[TickerCandidate]) -> List[TickerCandidate]:
    """Normalize tickers, calibrate confidence, dedupe by symbol."""
    by_ticker: Dict[str, TickerCandidate] = {}
    for c in candidates:
        sym = c.ticker.strip().upper()
        if not sym:
            continue
        try:
            sym = normalize_ticker(sym)
        except ValueError:
            continue
        conf = calibrate_confidence(float(c.confidence))
        market = c.market if c.market != TickerMarket.us else _infer_market(sym)
        existing = by_ticker.get(sym)
        if existing is None or conf > existing.confidence:
            by_ticker[sym] = TickerCandidate(
                ticker=sym,
                company_name=c.company_name,
                confidence=round(conf, 3),
                rationale=c.rationale,
                market=market,
            )
    return sorted(by_ticker.values(), key=lambda x: x.confidence, reverse=True)


def extract_from_articles(
    articles: List[TopicArticle],
    query: str,
    service_config: Dict[str, Any],
) -> ExtractionResult:
    """Run LLM structured extraction over Tavily articles."""
    if not articles:
        return ExtractionResult(
            theme_summary=f"No recent articles found for “{query}”.",
            candidates=[],
        )

    llm = _build_llm(service_config)
    user = _articles_to_prompt(articles, query)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]

    result: Any = None
    try:
        structured = llm.with_structured_output(ExtractionResult)
        result = structured.invoke(messages)
    except Exception as exc:
        logger.warning("Topics structured extraction failed: %s", exc)

    if isinstance(result, ExtractionResult):
        candidates = normalize_candidates(result.candidates)
        return ExtractionResult(theme_summary=result.theme_summary.strip(), candidates=candidates)

    if isinstance(result, dict):
        try:
            parsed = ExtractionResult.model_validate(result)
            candidates = normalize_candidates(parsed.candidates)
            return ExtractionResult(theme_summary=parsed.theme_summary.strip(), candidates=candidates)
        except Exception:
            pass

    # JSON fallback
    try:
        raw = llm.invoke(messages)
        text = getattr(raw, "content", raw)
        if not isinstance(text, str):
            text = str(text)
        parsed = ExtractionResult.model_validate(_first_json_object(text))
        candidates = normalize_candidates(parsed.candidates)
        return ExtractionResult(theme_summary=parsed.theme_summary.strip(), candidates=candidates)
    except Exception as exc:
        logger.warning("Topics extraction fallback failed: %s", exc)
        return ExtractionResult(
            theme_summary=f"Articles discuss “{query}”, but ticker extraction failed.",
            candidates=[],
        )
