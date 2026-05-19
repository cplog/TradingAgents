"""Pydantic schemas for Kronos forecast payloads."""
from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel


class KronosForecastRow(BaseModel):
    """One bar of OHLCV at a specific date (historical or forecast)."""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float


class KronosForecastPayload(BaseModel):
    """Complete Kronos forecast result for a single ticker/date."""
    ticker: str
    trade_date: str
    model: str
    tokenizer: str
    device: str
    lookback: int
    pred_len: int
    sample_count: int
    history_tail: List[KronosForecastRow]
    forecast: List[KronosForecastRow]
    generated_at: str


class KronosStatus(str, Enum):
    ok = "ok"
    disabled = "disabled"
    insufficient_data = "insufficient_data"
    load_failed = "load_failed"
    predict_failed = "predict_failed"
    timeout = "timeout"
