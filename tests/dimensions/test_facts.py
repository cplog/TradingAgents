import json
import math
from pathlib import Path

import pandas as pd
import pytest

from api.dimensions.facts import extract_facts, FactExtractionError

FIXTURES = Path(__file__).parent / "fixtures"


class _FakeTicker:
    def __init__(self, info, history_df=None):
        self.info = info
        self._history = history_df

    def history(self, *_args, **_kwargs):
        return self._history


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def _linear_history(n: int = 260, start: float = 100.0, end: float = 200.0, volume: float = 1e6):
    """Build a synthetic daily-bar DataFrame with linearly rising closes."""
    closes = [start + (end - start) * i / (n - 1) for i in range(n)]
    return pd.DataFrame({"Close": closes, "Volume": [volume] * n})


def test_extract_facts_aapl_happy_path(monkeypatch):
    info = _load("yfinance_aapl.json")
    df = _linear_history()
    monkeypatch.setattr(
        "api.dimensions.facts._yf_ticker",
        lambda t: _FakeTicker(info, df),
    )
    facts, flags = extract_facts("AAPL", "2026-05-13")
    assert facts.currency == "USD"
    assert facts.sector == "Technology"
    assert facts.pe_ttm == pytest.approx(info["trailingPE"])
    assert facts.market_cap_usd == pytest.approx(info["marketCap"])
    assert "missing_sector" not in flags

    # Price-history-derived fields should be populated from the synthetic DF.
    assert facts.return_1m is not None and facts.return_1m > 0
    assert facts.return_3m is not None and facts.return_3m > 0
    assert facts.return_12m is not None
    assert facts.realized_vol_30d is not None
    assert "missing_return_1m" not in flags
    assert "missing_return_12m" not in flags
    assert "missing_realized_vol_30d" not in flags


def test_extract_facts_handles_missing_fields(monkeypatch):
    sparse = {"currency": "USD", "regularMarketPrice": 100.0}
    monkeypatch.setattr(
        "api.dimensions.facts._yf_ticker",
        lambda t: _FakeTicker(sparse, None),
    )
    facts, flags = extract_facts("XYZ", "2026-05-13")
    assert facts.pe_ttm is None
    assert facts.sector is None
    assert "missing_sector" in flags
    assert "missing_pe_ttm" in flags
    # Empty history means all price-history-derived fields are flagged.
    assert "missing_return_1m" in flags
    assert "missing_rsi_14" in flags
    assert "missing_analyst_count" in flags


def test_extract_facts_hk_ticker_currency(monkeypatch):
    info = _load("yfinance_0700hk.json")
    monkeypatch.setattr(
        "api.dimensions.facts._yf_ticker",
        lambda t: _FakeTicker(info, None),
    )
    facts, _ = extract_facts("0700.HK", "2026-05-13")
    assert facts.currency == "HKD"
    assert facts.exchange == "HKG"


def test_extract_facts_string_forward_pe_coerced(monkeypatch):
    """yfinance occasionally returns numeric fields as strings."""
    info = {"currency": "USD", "forwardPE": "25.4"}
    monkeypatch.setattr(
        "api.dimensions.facts._yf_ticker",
        lambda t: _FakeTicker(info, None),
    )
    facts, _ = extract_facts("ABC", "2026-05-13")
    assert facts.forward_pe == pytest.approx(25.4)


def test_extract_facts_propagates_yfinance_error(monkeypatch):
    def boom(_t):
        raise RuntimeError("network down")
    monkeypatch.setattr("api.dimensions.facts._yf_ticker", boom)
    with pytest.raises(FactExtractionError):
        extract_facts("AAPL", "2026-05-13")


def test_extract_facts_populates_price_history_derived(monkeypatch):
    """Verify all price-history-derived fields are populated from a 260-row DF.

    Synthetic closes rise linearly 100 → 200 over 260 trading days with
    constant volume 1e6. Expected values:
      - return_12m: ~1.0 (price doubled over 252-day lookback)
      - return_1m:  positive
      - realized_vol_30d: small but > 0 (linear ramp ≠ flat)
      - rsi_14: between 0 and 100 (all gains → near 100)
      - avg_daily_dollar_volume_30d: positive (≈ price * 1e6 averaged)
    """
    info = {"currency": "USD"}
    df = _linear_history(n=260, start=100.0, end=200.0, volume=1e6)
    monkeypatch.setattr(
        "api.dimensions.facts._yf_ticker",
        lambda t: _FakeTicker(info, df),
    )
    facts, flags = extract_facts("LIN", "2026-05-13")

    # return_12m ≈ (close[-1] / close[-1 - 252]) - 1.
    last = 200.0
    prior_12m = 100.0 + (200.0 - 100.0) * (260 - 1 - 252) / (260 - 1)
    expected_return_12m = (last / prior_12m) - 1.0
    assert facts.return_12m == pytest.approx(expected_return_12m, rel=1e-6)

    assert facts.return_1m is not None and facts.return_1m > 0
    assert facts.return_3m is not None and facts.return_3m > 0
    assert facts.return_6m is not None and facts.return_6m > 0

    assert facts.realized_vol_30d is not None
    assert math.isfinite(facts.realized_vol_30d)
    assert facts.realized_vol_30d > 0

    assert facts.rsi_14 is not None
    assert 0.0 <= facts.rsi_14 <= 100.0

    assert facts.avg_daily_dollar_volume_30d is not None
    assert facts.avg_daily_dollar_volume_30d > 0
    # Closes in last 30 rows range roughly 188.8 → 200.0; mean × 1e6 should
    # be on the order of 1.94e8.
    assert facts.avg_daily_dollar_volume_30d == pytest.approx(1.94e8, rel=1e-2)

    # No missing_* flags for the price-history-derived fields.
    for f in (
        "return_1m",
        "return_3m",
        "return_6m",
        "return_12m",
        "realized_vol_30d",
        "rsi_14",
        "avg_daily_dollar_volume_30d",
    ):
        assert f"missing_{f}" not in flags
