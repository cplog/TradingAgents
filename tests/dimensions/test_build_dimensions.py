from pathlib import Path
from unittest.mock import MagicMock

import pytest

from api.dimensions.builder import (
    build_dimensions, build_dimensions_facts_only, DimensionsBuildError,
)
from api.dimensions.schemas import (
    FactSnapshot, PillarScores, MarketPillar, SentimentPillar, NewsPillar,
    FundamentalsPillar, PillarScore, StockDimensions,
)


def _ps(s=3):
    return PillarScore(score=s, rationale="x")


def _valid_pillars():
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


def _stub_facts():
    return FactSnapshot(
        as_of_date="2026-05-13", currency="USD", sector="Technology",
        industry="Consumer Electronics", pe_ttm=28.0, pb=45.0, eps_growth_yoy=0.08,
    )


@pytest.fixture
def patch_modules(monkeypatch, tmp_path):
    monkeypatch.setattr("api.dimensions.builder.extract_facts",
                       lambda t, d: (_stub_facts(), []))
    monkeypatch.setattr("api.dimensions.builder.score_pillars",
                       lambda **k: _valid_pillars())
    monkeypatch.setattr(
        "api.dimensions.builder._get_peer_cache_dir",
        lambda cfg: tmp_path,
    )
    # Stub peer loading to return empty (forces absolute fallback)
    monkeypatch.setattr(
        "api.dimensions.builder._load_or_refresh_peers",
        lambda *a, **k: ([], {}),
    )


def test_build_dimensions_happy_path(patch_modules):
    fake_llm = MagicMock()
    reports = {"market": "x", "social": "y", "news": "z", "fundamentals": "w"}
    out = build_dimensions(
        ticker="AAPL", as_of_date="2026-05-13",
        analyst_reports=reports, llm=fake_llm, config={"data_cache_dir": "/tmp"},
    )
    assert isinstance(out, StockDimensions)
    assert out.ticker == "AAPL"
    assert out.source == "full_run"
    assert out.dimensions_version == "1.0.0"


def test_build_dimensions_facts_only_uses_neutral_pillars(monkeypatch, tmp_path):
    monkeypatch.setattr("api.dimensions.builder.extract_facts",
                       lambda t, d: (_stub_facts(), []))
    monkeypatch.setattr("api.dimensions.builder._get_peer_cache_dir",
                       lambda cfg: tmp_path)
    monkeypatch.setattr("api.dimensions.builder._load_or_refresh_peers",
                       lambda *a, **k: ([], {}))
    out = build_dimensions_facts_only(
        ticker="AAPL", as_of_date="2026-05-13", config={"data_cache_dir": "/tmp"},
    )
    assert out.source == "facts_only"
    # Neutral pillars: every pillar score should be 3
    assert out.pillar_scores.market.trend.score == 3
    assert out.pillar_scores.fundamentals.valuation.score == 3


def test_build_dimensions_raises_on_fact_extraction_failure(monkeypatch, tmp_path):
    from api.dimensions.facts import FactExtractionError
    def boom(t, d): raise FactExtractionError("network")
    monkeypatch.setattr("api.dimensions.builder.extract_facts", boom)
    monkeypatch.setattr("api.dimensions.builder._get_peer_cache_dir",
                       lambda cfg: tmp_path)
    with pytest.raises(DimensionsBuildError):
        build_dimensions(
            ticker="AAPL", as_of_date="2026-05-13",
            analyst_reports={}, llm=MagicMock(), config={},
        )


def test_build_dimensions_peer_universe_id_populated(patch_modules):
    fake_llm = MagicMock()
    out = build_dimensions(
        ticker="AAPL", as_of_date="2026-05-13",
        analyst_reports={"market": "x"}, llm=fake_llm, config={},
    )
    assert out.peer_universe_id == "sector:Technology|industry:Consumer Electronics"
