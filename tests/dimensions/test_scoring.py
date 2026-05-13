import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from api.dimensions.scoring import score_pillars, PillarScoringError
from api.dimensions.schemas import (
    PillarScores, MarketPillar, SentimentPillar, NewsPillar, FundamentalsPillar,
    PillarScore, FactSnapshot,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _ps(s=3, w="ok"):
    return PillarScore(score=s, rationale=w)


def _make_valid_pillars():
    return PillarScores(
        market=MarketPillar(trend=_ps(4), momentum=_ps(4), volatility_risk=_ps(3),
                            setup_quality=_ps(3)),
        sentiment=SentimentPillar(retail_sentiment=_ps(3), social_buzz=_ps(3),
                                 consensus_quality=_ps(3), narrative_strength=_ps(3)),
        news=NewsPillar(catalyst_strength=_ps(3), macro_alignment=_ps(3),
                       headline_quality=_ps(3), surprise_risk=_ps(3)),
        fundamentals=FundamentalsPillar(valuation=_ps(4), growth=_ps(4),
                                       profitability=_ps(4), balance_sheet_strength=_ps(4)),
    )


def test_score_pillars_invokes_structured_output(monkeypatch):
    captured = {}

    class FakeStructured:
        def invoke(self, messages):
            captured["messages"] = messages
            return _make_valid_pillars()

    fake_llm = MagicMock()
    fake_llm.with_structured_output = MagicMock(return_value=FakeStructured())

    facts = FactSnapshot(as_of_date="2026-05-13", currency="USD", pe_ttm=28.0)
    reports = {"market": "trend up", "fundamentals": "good moat"}
    out = score_pillars(facts=facts, analyst_reports=reports, llm=fake_llm)

    assert isinstance(out, PillarScores)
    fake_llm.with_structured_output.assert_called_once()
    # Prompt content should reference the analyst reports + facts
    msg_text = json.dumps(captured["messages"], default=str)
    assert "trend up" in msg_text
    assert "good moat" in msg_text
    assert "28.0" in msg_text or "pe_ttm" in msg_text


def test_score_pillars_raises_on_structured_failure():
    class BoomStructured:
        def invoke(self, _messages):
            raise ValueError("schema mismatch")
    fake_llm = MagicMock()
    fake_llm.with_structured_output = MagicMock(return_value=BoomStructured())

    facts = FactSnapshot(as_of_date="2026-05-13", currency="USD")
    with pytest.raises(PillarScoringError):
        score_pillars(facts=facts, analyst_reports={}, llm=fake_llm)


def test_score_pillars_handles_empty_reports():
    fake_llm = MagicMock()
    fake_llm.with_structured_output = MagicMock(
        return_value=MagicMock(invoke=MagicMock(return_value=_make_valid_pillars()))
    )
    facts = FactSnapshot(as_of_date="2026-05-13", currency="USD")
    out = score_pillars(facts=facts, analyst_reports={}, llm=fake_llm)
    assert isinstance(out, PillarScores)
