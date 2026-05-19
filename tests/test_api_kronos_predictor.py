"""Tests for api/kronos/predictor.py — uses a fake upstream KronosPredictor."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from api.kronos.config import KronosConfig
from api.kronos.errors import InsufficientData, ModelLoadError
from api.kronos.schema import KronosForecastPayload


def _ohlcv_fixture(n: int = 200) -> pd.DataFrame:
    ts = pd.date_range(end="2026-05-18", periods=n, freq="B")
    return pd.DataFrame({
        "timestamps": ts,
        "open": [100.0] * n,
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": [100.5] * n,
        "volume": [1_000_000.0] * n,
        "amount": [100_500_000.0] * n,
    })


class _FakePredictor:
    def __init__(self, *args, **kwargs):
        self.init_kwargs = kwargs

    def predict(self, df, x_timestamp, y_timestamp, pred_len, T, top_p,
                sample_count, **kw):
        return pd.DataFrame({
            "open": [100.0] * pred_len,
            "high": [102.0] * pred_len,
            "low": [98.0] * pred_len,
            "close": [101.0] * pred_len,
            "volume": [1_500_000.0] * pred_len,
            "amount": [151_500_000.0] * pred_len,
        }, index=list(y_timestamp))


def _install_fake_model_module(monkeypatch):
    """Inject a fake ``model`` module into sys.modules so the predictor
    can import upstream classes without a real vendor/kronos/ clone."""
    fake_model = types.ModuleType("model")
    fake_model.Kronos = MagicMock(name="Kronos")
    fake_model.Kronos.from_pretrained = MagicMock(return_value=MagicMock())
    fake_model.KronosTokenizer = MagicMock(name="KronosTokenizer")
    fake_model.KronosTokenizer.from_pretrained = MagicMock(return_value=MagicMock())
    fake_model.KronosPredictor = _FakePredictor
    monkeypatch.setitem(sys.modules, "model", fake_model)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Each test gets a fresh KronosService singleton."""
    from api.kronos.predictor import KronosService
    KronosService.reset()
    yield
    KronosService.reset()


def test_forecast_returns_well_formed_payload(monkeypatch):
    _install_fake_model_module(monkeypatch)
    from api.kronos.predictor import KronosService

    cfg = KronosConfig(lookback=200, pred_len=20, sample_count=1, device="cpu")
    svc = KronosService.get(cfg)
    payload = svc.forecast(_ohlcv_fixture(200), ticker="AAPL", trade_date="2026-05-19")

    assert isinstance(payload, KronosForecastPayload)
    assert payload.ticker == "AAPL"
    assert payload.trade_date == "2026-05-19"
    assert payload.model == "NeoQuasar/Kronos-small"
    assert payload.lookback == 200
    assert payload.pred_len == 20
    assert payload.sample_count == 1
    assert payload.device == "cpu"
    assert len(payload.forecast) == 20
    assert payload.forecast[0].close == 101.0
    assert payload.forecast[0].open == 100.0
    assert len(payload.history_tail) <= 20
    assert payload.history_tail[-1].close == 100.5


def test_forecast_raises_insufficient_data_when_short(monkeypatch):
    _install_fake_model_module(monkeypatch)
    from api.kronos.predictor import KronosService

    cfg = KronosConfig(lookback=200, pred_len=20, sample_count=1, device="cpu")
    svc = KronosService.get(cfg)
    with pytest.raises(InsufficientData):
        svc.forecast(_ohlcv_fixture(50), ticker="AAPL", trade_date="2026-05-19")


def test_model_load_error_when_vendor_missing(monkeypatch):
    """If 'model' cannot be imported, ModelLoadError is raised."""
    monkeypatch.setitem(sys.modules, "model", None)
    from api.kronos.predictor import KronosService

    cfg = KronosConfig(device="cpu")
    svc = KronosService.get(cfg)
    with pytest.raises(ModelLoadError):
        svc.forecast(_ohlcv_fixture(200), ticker="AAPL", trade_date="2026-05-19")


def test_singleton_is_reused(monkeypatch):
    _install_fake_model_module(monkeypatch)
    from api.kronos.predictor import KronosService

    cfg = KronosConfig(device="cpu")
    a = KronosService.get(cfg)
    b = KronosService.get(cfg)
    assert a is b


def test_lazy_load_happens_once(monkeypatch):
    _install_fake_model_module(monkeypatch)
    fake_model = sys.modules["model"]
    from api.kronos.predictor import KronosService

    cfg = KronosConfig(device="cpu")
    svc = KronosService.get(cfg)
    svc.forecast(_ohlcv_fixture(200), "AAPL", "2026-05-19")
    svc.forecast(_ohlcv_fixture(200), "AAPL", "2026-05-19")

    assert fake_model.KronosTokenizer.from_pretrained.call_count == 1
    assert fake_model.Kronos.from_pretrained.call_count == 1
