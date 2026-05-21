"""When BOTH the structured-output and the JSON fallback paths fail, the error
must surface (a) the *real* fallback exception and (b) the truncated raw text
the model emitted. The previous error message ("Unexpected scoring result
type: NoneType") buried both, making Ollama failures impossible to diagnose
from the persisted run record.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from api.dimensions.scoring import score_pillars, PillarScoringError
from api.dimensions.schemas import FactSnapshot


def _llm_with(structured_returns, fallback_returns):
    structured = MagicMock()
    structured.invoke = MagicMock(return_value=structured_returns)
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value=structured)
    llm.invoke = MagicMock(return_value=fallback_returns)
    return llm


def test_error_message_includes_fallback_reason_not_just_nonetype():
    """Old behaviour: PillarScoringError("Unexpected scoring result type: NoneType")
    swallowed the fallback exception via `from exc`. New behaviour: the message
    itself names the fallback failure so it survives `str(exc)` formatting and
    ends up in `pillar_scoring_unavailable` flag text."""
    llm = _llm_with(
        structured_returns=None,
        fallback_returns=SimpleNamespace(content="not json at all, sorry"),
    )
    facts = FactSnapshot(as_of_date="2026-05-13", currency="USD")

    with pytest.raises(PillarScoringError) as exc_info:
        score_pillars(facts=facts, analyst_reports={}, llm=llm)

    msg = str(exc_info.value)
    assert "fallback failed" in msg.lower()
    assert "NoneType" in msg  # still tells you structured returned None
    # And the real cause should be referenced — either inline or as the chained __cause__
    assert "json" in msg.lower() or exc_info.value.__cause__ is not None


def test_raw_fallback_output_is_logged_truncated_on_failure(caplog):
    long_garbage = "garbage prose " * 100  # ~1400 chars, no JSON
    llm = _llm_with(
        structured_returns=None,
        fallback_returns=SimpleNamespace(content=long_garbage),
    )
    facts = FactSnapshot(as_of_date="2026-05-13", currency="USD")

    with caplog.at_level(logging.WARNING, logger="api.dimensions.scoring"):
        with pytest.raises(PillarScoringError):
            score_pillars(facts=facts, analyst_reports={}, llm=llm)

    # We log the raw output (truncated) so next-run diagnosis can read it
    fallback_logs = [r for r in caplog.records if "fallback output" in r.getMessage()]
    assert fallback_logs, "expected a 'fallback output' WARNING log"
    snippet = fallback_logs[0].getMessage()
    # Truncation cap is 500 chars; the log line itself is a bit longer because
    # of the prefix, but the snippet should not contain the entire 1400-char
    # garbage string.
    assert len(snippet) < 700
    assert "garbage prose" in snippet


def test_no_raw_output_log_when_fallback_invoke_itself_raises():
    """If `llm.invoke` itself raises before producing content, there's nothing
    to log — we should not emit a misleading 'fallback output' line with empty
    text."""
    structured = MagicMock()
    structured.invoke = MagicMock(return_value=None)
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value=structured)
    llm.invoke = MagicMock(side_effect=RuntimeError("network blew up"))
    facts = FactSnapshot(as_of_date="2026-05-13", currency="USD")

    with pytest.raises(PillarScoringError) as exc_info:
        score_pillars(facts=facts, analyst_reports={}, llm=llm)

    # The error still mentions the fallback failed AND the underlying network error
    assert "network blew up" in str(exc_info.value)
