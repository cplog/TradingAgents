"""Live Kronos smoke test — loads the real model from HF Hub.

OPT-IN ONLY. Excluded from default CI. Run with:
    pytest -m kronos_live -v
"""
from __future__ import annotations

import pandas as pd
import pytest

from api.kronos import KronosConfig, KronosService
from api.kronos.predictor import _VENDOR_KRONOS


pytestmark = pytest.mark.kronos_live


@pytest.fixture(autouse=True)
def _reset_singleton():
    KronosService.reset()
    yield
    KronosService.reset()


def _synthetic_ohlcv(n: int = 200) -> pd.DataFrame:
    ts = pd.date_range(end="2026-05-18", periods=n, freq="B")
    base = 100.0
    closes = [base + i * 0.5 for i in range(n)]
    return pd.DataFrame({
        "timestamps": ts,
        "open":   [c - 0.5 for c in closes],
        "high":   [c + 1.0 for c in closes],
        "low":    [c - 1.0 for c in closes],
        "close":  closes,
        "volume": [1_000_000.0] * n,
        "amount": [c * 1_000_000.0 for c in closes],
    })


def test_vendor_kronos_clone_exists():
    """Live tests presume scripts/dev_up.sh has been run."""
    assert (_VENDOR_KRONOS / "model" / "__init__.py").exists(), (
        f"vendor/kronos not found at {_VENDOR_KRONOS} — run scripts/dev_up.sh"
    )


def test_real_kronos_small_forecast_smoke():
    """End-to-end load + forecast against the real Kronos-small model."""
    cfg = KronosConfig(
        model="NeoQuasar/Kronos-small",
        tokenizer="NeoQuasar/Kronos-Tokenizer-base",
        device="cpu",  # don't assume GPU/MPS in the smoke test
        lookback=200,
        pred_len=10,
        sample_count=1,
        max_context=512,
    )
    svc = KronosService.get(cfg)
    payload = svc.forecast(
        _synthetic_ohlcv(200), ticker="SMOKE", trade_date="2026-05-19",
    )
    assert payload.ticker == "SMOKE"
    assert len(payload.forecast) == 10
    # Close prices should be finite floats, not NaN/Inf
    for row in payload.forecast:
        assert row.close > 0
        assert row.close == row.close  # NaN check
