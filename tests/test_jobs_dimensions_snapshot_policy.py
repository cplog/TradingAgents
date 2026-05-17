from api.jobs import _should_rebuild_graph_dimensions_snapshot


def _snapshot_with_style_scores(score):
    return {
        "source": "full_run",
        "factor_scores": {
            "value": {"score": score},
            "growth": {"score": score},
            "quality": {"score": score},
            "momentum": {"score": score},
            "low_risk": {"score": score},
            "sentiment": {"score": 50.0},
        },
    }


def test_rebuild_when_full_run_has_all_empty_style_scores():
    snap = _snapshot_with_style_scores(None)
    assert _should_rebuild_graph_dimensions_snapshot(snap) is True


def test_keep_snapshot_when_any_style_score_present():
    snap = _snapshot_with_style_scores(None)
    snap["factor_scores"]["value"]["score"] = 42.0
    assert _should_rebuild_graph_dimensions_snapshot(snap) is False


def test_keep_snapshot_for_facts_only_even_if_style_scores_empty():
    snap = _snapshot_with_style_scores(None)
    snap["source"] = "facts_only"
    assert _should_rebuild_graph_dimensions_snapshot(snap) is False
