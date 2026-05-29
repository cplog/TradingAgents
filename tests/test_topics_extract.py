"""Topics LLM extraction tests."""

from __future__ import annotations

import pytest

from api.topics_extract import calibrate_confidence, normalize_candidates
from api.topics_models import TickerCandidate, TickerMarket, TopicArticle
from api.topics_extract import extract_from_articles


@pytest.mark.unit
def test_calibrate_confidence():
    assert calibrate_confidence(0.95) >= 0.85
    assert calibrate_confidence(0.5) < calibrate_confidence(0.8)
    assert calibrate_confidence(0.1) <= 0.1


@pytest.mark.unit
def test_normalize_candidates_dedupes():
    raw = [
        TickerCandidate(ticker="aapl", confidence=0.7, market=TickerMarket.us),
        TickerCandidate(ticker="AAPL", confidence=0.9, market=TickerMarket.us),
        TickerCandidate(ticker="../bad", confidence=0.9, market=TickerMarket.us),
    ]
    out = normalize_candidates(raw)
    assert len(out) == 1
    assert out[0].ticker == "AAPL"
    assert out[0].confidence == calibrate_confidence(0.9)


@pytest.mark.unit
def test_extract_empty_articles():
    result = extract_from_articles([], "AI theme", {"llm_provider": "openai", "quick_think_llm": "gpt-4o-mini"})
    assert "No recent articles" in result.theme_summary
    assert result.candidates == []


@pytest.mark.unit
def test_extract_with_mock_llm(monkeypatch):
    from api.topics_models import ExtractionResult

    class FakeStructured:
        def invoke(self, messages):
            return ExtractionResult(
                theme_summary="AI infra is hot.",
                candidates=[TickerCandidate(ticker="NVDA", confidence=0.92, market=TickerMarket.us)],
            )

    class FakeLLM:
        def with_structured_output(self, schema):
            return FakeStructured()

    monkeypatch.setattr("api.topics_extract._build_llm", lambda cfg: FakeLLM())
    articles = [TopicArticle(title="NVDA", url="https://x.com", snippet="NVIDIA")]
    result = extract_from_articles(articles, "AI", {"llm_provider": "openai"})
    assert result.candidates[0].ticker == "NVDA"
    assert "AI infra" in result.theme_summary
