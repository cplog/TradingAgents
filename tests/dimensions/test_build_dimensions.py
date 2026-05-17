from unittest.mock import MagicMock

import pytest

from api.dimensions.builder import (
    build_dimensions,
    build_dimensions_facts_only,
    DimensionsBuildError,
)
from api.dimensions.peer_resolver import PeerFactsResolution
from api.dimensions.peers import peer_universe_id
from api.dimensions.schemas import (
    FactSnapshot,
    PillarScores,
    MarketPillar,
    SentimentPillar,
    NewsPillar,
    FundamentalsPillar,
    PillarScore,
    StockDimensions,
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


def _empty_peer_resolution(facts: FactSnapshot, peer_dir) -> PeerFactsResolution:
    lbls = []
    if facts.sector and facts.industry:
        lbls.append(peer_universe_id(facts.sector, facts.industry))
    return PeerFactsResolution(
        facts_by_ticker={},
        slug_used=None,
        peer_scope="unavailable",
        peer_universe_label=None,
        search_path_labels=lbls,
        escalation_flags=["peer_percentiles_cache_miss"],
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
    monkeypatch.setattr(
        "api.dimensions.builder.resolve_peer_facts_for_snapshot",
        _empty_peer_resolution,
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
    assert out.peer_scope == "unavailable"
    assert out.factor_scores.value.score is not None
    assert "peer_percentiles_unavailable" in out.data_quality_flags


def test_build_dimensions_facts_only_uses_neutral_pillars(monkeypatch, tmp_path):
    monkeypatch.setattr("api.dimensions.builder.extract_facts",
                       lambda t, d: (_stub_facts(), []))
    monkeypatch.setattr("api.dimensions.builder._get_peer_cache_dir",
                       lambda cfg: tmp_path)
    monkeypatch.setattr(
        "api.dimensions.builder.resolve_peer_facts_for_snapshot",
        _empty_peer_resolution,
    )
    out = build_dimensions_facts_only(
        ticker="AAPL", as_of_date="2026-05-13", config={"data_cache_dir": "/tmp"},
    )
    assert out.source == "facts_only"
    assert out.pillar_scores.market.trend.score == 3
    assert out.pillar_scores.fundamentals.valuation.score == 3
    assert out.factor_scores.value.score is None
    assert out.factor_scores.sentiment.score is not None
    assert "peer_percentiles_unavailable" in out.data_quality_flags


def test_build_dimensions_raises_on_fact_extraction_failure(monkeypatch, tmp_path):
    from api.dimensions.facts import FactExtractionError

    def boom(t, d):
        raise FactExtractionError("network")

    monkeypatch.setattr("api.dimensions.builder.extract_facts", boom)
    monkeypatch.setattr("api.dimensions.builder._get_peer_cache_dir",
                         lambda cfg: tmp_path)
    with pytest.raises(DimensionsBuildError):
        build_dimensions(
            ticker="AAPL", as_of_date="2026-05-13",
            analyst_reports={}, llm=MagicMock(), config={},
        )


def test_build_dimensions_peer_universe_path_populated(patch_modules):
    fake_llm = MagicMock()
    out = build_dimensions(
        ticker="AAPL", as_of_date="2026-05-13",
        analyst_reports={"market": "x"}, llm=fake_llm, config={},
    )
    assert out.peer_universe_id == peer_universe_id("Technology", "Consumer Electronics")


def test_build_dimensions_falls_back_to_neutral_when_scoring_unavailable(monkeypatch, tmp_path):
    from api.dimensions.scoring import PillarScoringError

    monkeypatch.setattr("api.dimensions.builder.extract_facts", lambda t, d: (_stub_facts(), []))
    monkeypatch.setattr("api.dimensions.builder._get_peer_cache_dir", lambda cfg: tmp_path)
    monkeypatch.setattr(
        "api.dimensions.builder.resolve_peer_facts_for_snapshot",
        _empty_peer_resolution,
    )

    def _boom(**_kwargs):
        raise PillarScoringError("Unexpected scoring result type: NoneType")

    monkeypatch.setattr("api.dimensions.builder.score_pillars", _boom)

    out = build_dimensions(
        ticker="BABA", as_of_date="2026-05-14",
        analyst_reports={"market": "x"}, llm=MagicMock(), config={},
    )
    assert out.source == "facts_only"
    assert out.pillar_scores.market.trend.score == 3
    assert any("pillar_scoring_unavailable" in flag for flag in out.data_quality_flags)
    # Neutral pillars + no peer universe: still show factor scores (pillar-only blend).
    assert out.factor_scores.value.score == pytest.approx(50.0)
    assert "peer_percentiles_unavailable" in out.data_quality_flags


def test_build_dimensions_facts_only_shows_factors_when_peers_warmed(monkeypatch, tmp_path):
    fake_peers = {
        "P1": {"pe_ttm": 15.0, "pb": 3.0, "eps_growth_yoy": 0.05, "revenue_growth_yoy": 0.04,
               "roe": 0.12, "interest_coverage": 8.0, "return_3m": 0.02, "return_12m": 0.1,
               "beta": 1.1},
        "P2": {"pe_ttm": 25.0, "pb": 5.0, "eps_growth_yoy": 0.10, "revenue_growth_yoy": 0.08,
               "roe": 0.18, "interest_coverage": 12.0, "return_3m": 0.05, "return_12m": 0.15,
               "beta": 1.0},
        "P3": {"pe_ttm": 35.0, "pb": 8.0, "eps_growth_yoy": 0.02, "revenue_growth_yoy": 0.01,
               "roe": 0.08, "interest_coverage": 5.0, "return_3m": -0.02, "return_12m": 0.05,
               "beta": 1.2},
    }

    def _warm(facts: FactSnapshot, peer_dir):
        return PeerFactsResolution(
            facts_by_ticker=fake_peers,
            slug_used="Technology__Consumer Electronics",
            peer_scope="global_fallback",
            peer_universe_label="sector:Technology|industry:Consumer Electronics",
            search_path_labels=["sector:Technology|industry:Consumer Electronics"],
            escalation_flags=["peer_scope_global_fallback"],
        )

    monkeypatch.setattr("api.dimensions.builder.extract_facts",
                       lambda t, d: (_stub_facts(), []))
    monkeypatch.setattr("api.dimensions.builder._get_peer_cache_dir",
                       lambda cfg: tmp_path)
    monkeypatch.setattr(
        "api.dimensions.builder.resolve_peer_facts_for_snapshot",
        _warm,
    )
    out = build_dimensions_facts_only(
        ticker="AAPL", as_of_date="2026-05-13", config={"data_cache_dir": "/tmp"},
    )
    assert out.source == "facts_only"
    assert out.peer_scope == "global_fallback"
    assert out.peer_universe_resolved_slug == "Technology__Consumer Electronics"
    assert "peer_percentiles_unavailable" not in out.data_quality_flags
    assert out.factor_scores.value.score is not None
    assert out.factor_scores.growth.score is not None
