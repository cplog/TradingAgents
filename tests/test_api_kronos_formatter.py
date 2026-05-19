"""Tests for api/kronos/formatter.py — markdown + JSON shaping."""
from __future__ import annotations

import json

import pytest

from api.kronos.formatter import forecast_to_markdown, forecast_to_state
from api.kronos.schema import KronosForecastPayload, KronosForecastRow


def _row(date: str, close: float) -> KronosForecastRow:
    return KronosForecastRow(
        date=date, open=close - 0.5, high=close + 1.0, low=close - 1.0,
        close=close, volume=1_000_000.0, amount=close * 1_000_000.0,
    )


def _payload(forecast_closes):
    return KronosForecastPayload(
        ticker="AAPL",
        trade_date="2026-05-19",
        model="NeoQuasar/Kronos-small",
        tokenizer="NeoQuasar/Kronos-Tokenizer-base",
        device="mps",
        lookback=200,
        pred_len=len(forecast_closes),
        sample_count=1,
        history_tail=[_row("2026-05-18", 150.0)],
        forecast=[_row(f"2026-05-{20+i:02d}", c) for i, c in enumerate(forecast_closes)],
        generated_at="2026-05-19T12:00:00+00:00",
    )


def test_markdown_includes_header_metadata_and_disclaimer():
    md = forecast_to_markdown(_payload([151.0, 152.0, 153.0]))
    assert "Kronos forecast" in md
    assert "AAPL" in md
    assert "2026-05-19" in md
    assert "NeoQuasar/Kronos-small" in md
    assert "mps" in md
    assert "200d" in md or "200 d" in md
    assert "Not investment advice" in md


def test_markdown_renders_a_table_row_per_forecast_day():
    md = forecast_to_markdown(_payload([151.0, 152.0, 153.0]))
    assert "2026-05-20" in md
    assert "2026-05-21" in md
    assert "2026-05-22" in md
    assert "151" in md
    assert "153" in md


def test_markdown_drift_narrative_uses_actual_numbers():
    md = forecast_to_markdown(_payload([155.0, 160.0, 165.0]))
    assert "150" in md
    assert "165" in md


def test_forecast_to_state_is_json_serializable():
    state = forecast_to_state(_payload([151.0, 152.0]))
    s = json.dumps(state)
    loaded = json.loads(s)
    assert loaded["ticker"] == "AAPL"
    assert loaded["pred_len"] == 2
    assert len(loaded["forecast"]) == 2
    assert loaded["forecast"][0]["close"] == 151.0


def test_forecast_to_state_none_returns_none():
    assert forecast_to_state(None) is None


def test_markdown_when_payload_is_none():
    assert forecast_to_markdown(None) == ""
