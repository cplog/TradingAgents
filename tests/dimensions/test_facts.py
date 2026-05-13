import json
from pathlib import Path

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


def test_extract_facts_aapl_happy_path(monkeypatch):
    info = _load("yfinance_aapl.json")
    import pandas as pd
    df = pd.DataFrame({"Close": [170.0, 175.0, 180.0, 185.0, 190.0]})
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
