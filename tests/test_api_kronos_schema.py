"""Schema + error class tests for api/kronos."""
import json
import pytest

from api.kronos.errors import KronosDisabled, InsufficientData, ModelLoadError
from api.kronos.schema import (
    KronosForecastRow,
    KronosForecastPayload,
    KronosStatus,
)


def test_errors_are_distinct_exception_classes():
    assert issubclass(KronosDisabled, Exception)
    assert issubclass(InsufficientData, Exception)
    assert issubclass(ModelLoadError, Exception)
    assert not issubclass(KronosDisabled, InsufficientData)


def test_forecast_row_round_trips_via_pydantic():
    row = KronosForecastRow(
        date="2026-05-20",
        open=100.5,
        high=101.2,
        low=99.8,
        close=100.9,
        volume=1_234_500.0,
        amount=124_563_405.0,
    )
    js = row.model_dump_json()
    restored = KronosForecastRow.model_validate_json(js)
    assert restored == row


def test_forecast_payload_round_trips():
    row = KronosForecastRow(
        date="2026-05-20", open=1.0, high=1.0, low=1.0,
        close=1.0, volume=1.0, amount=1.0,
    )
    payload = KronosForecastPayload(
        ticker="AAPL",
        trade_date="2026-05-19",
        model="NeoQuasar/Kronos-small",
        tokenizer="NeoQuasar/Kronos-Tokenizer-base",
        device="mps",
        lookback=200,
        pred_len=20,
        sample_count=1,
        history_tail=[row],
        forecast=[row, row],
        generated_at="2026-05-19T12:00:00Z",
    )
    js = payload.model_dump_json()
    restored = KronosForecastPayload.model_validate_json(js)
    assert restored == payload
    assert len(restored.forecast) == 2


def test_kronos_status_values():
    assert KronosStatus("ok").value == "ok"
    assert {s.value for s in KronosStatus} == {
        "ok", "disabled", "insufficient_data",
        "load_failed", "predict_failed", "timeout",
    }
