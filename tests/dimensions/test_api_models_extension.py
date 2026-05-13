from api.models import (
    AnalysisResult, HistoryRunDetail, HistoryRunRef, HistoryCompareSide,
)


def test_analysis_result_accepts_dimensions_fields():
    payload = {
        "ticker": "AAPL", "date": "2026-05-13", "rating": "Buy",
        "reports": {}, "completed_at": "2026-05-13T00:00:00Z",
        "dimensions": None,
        "dimensions_commentary": None,
        "dimensions_error": None,
    }
    m = AnalysisResult.model_validate(payload)
    assert m.dimensions is None
    assert m.dimensions_commentary is None


def test_history_run_ref_factor_scores_optional():
    ref = HistoryRunRef(run_id="x", factor_scores={"value": 70.0})
    assert ref.factor_scores == {"value": 70.0}
    ref2 = HistoryRunRef(run_id="y")
    assert ref2.factor_scores is None


def test_history_run_detail_round_trips_with_dimensions_none():
    detail = HistoryRunDetail(
        run_id="r1", job_id="j1", ticker="AAPL", date="2026-05-13", rating="Buy",
        dimensions=None, dimensions_commentary=None,
    )
    dumped = detail.model_dump()
    HistoryRunDetail.model_validate(dumped)


def test_compare_side_accepts_dimensions_field():
    side = HistoryCompareSide(dimensions=None)
    assert side.dimensions is None
