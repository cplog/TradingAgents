"""Config / env-loader tests for api/kronos."""
import pytest

from api.kronos.config import KronosConfig


def test_defaults_match_spec(monkeypatch):
    for k in [
        "KRONOS_ENABLED", "KRONOS_MODEL", "KRONOS_TOKENIZER", "KRONOS_DEVICE",
        "KRONOS_LOOKBACK", "KRONOS_PRED_LEN", "KRONOS_SAMPLE_COUNT",
        "KRONOS_T", "KRONOS_TOP_P", "KRONOS_TIMEOUT_SECONDS", "KRONOS_MAX_CONTEXT",
    ]:
        monkeypatch.delenv(k, raising=False)
    cfg = KronosConfig.from_env()
    assert cfg.enabled is True
    assert cfg.model == "NeoQuasar/Kronos-small"
    assert cfg.tokenizer == "NeoQuasar/Kronos-Tokenizer-base"
    assert cfg.device == "auto"
    assert cfg.lookback == 200
    assert cfg.pred_len == 20
    assert cfg.sample_count == 1
    assert cfg.temperature == 1.0
    assert cfg.top_p == 0.9
    assert cfg.timeout_seconds == 90
    assert cfg.max_context == 512


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("KRONOS_ENABLED", "false")
    monkeypatch.setenv("KRONOS_MODEL", "NeoQuasar/Kronos-base")
    monkeypatch.setenv("KRONOS_DEVICE", "cpu")
    monkeypatch.setenv("KRONOS_LOOKBACK", "120")
    monkeypatch.setenv("KRONOS_PRED_LEN", "10")
    monkeypatch.setenv("KRONOS_SAMPLE_COUNT", "5")
    monkeypatch.setenv("KRONOS_T", "0.7")
    monkeypatch.setenv("KRONOS_TIMEOUT_SECONDS", "30")
    cfg = KronosConfig.from_env()
    assert cfg.enabled is False
    assert cfg.model == "NeoQuasar/Kronos-base"
    assert cfg.device == "cpu"
    assert cfg.lookback == 120
    assert cfg.pred_len == 10
    assert cfg.sample_count == 5
    assert cfg.temperature == 0.7
    assert cfg.timeout_seconds == 30


def test_env_bool_truthy_variants(monkeypatch):
    for val in ("1", "true", "TRUE", "yes", "on", "True"):
        monkeypatch.setenv("KRONOS_ENABLED", val)
        assert KronosConfig.from_env().enabled is True
    for val in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("KRONOS_ENABLED", val)
        assert KronosConfig.from_env().enabled is False


def test_invalid_int_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("KRONOS_LOOKBACK", "not-a-number")
    cfg = KronosConfig.from_env()
    assert cfg.lookback == 200


def test_resolved_device_passes_through_explicit_setting(monkeypatch):
    monkeypatch.setenv("KRONOS_DEVICE", "cpu")
    cfg = KronosConfig.from_env()
    assert cfg.resolved_device == "cpu"


def test_resolved_device_auto_picks_a_real_device(monkeypatch):
    monkeypatch.setenv("KRONOS_DEVICE", "auto")
    cfg = KronosConfig.from_env()
    assert cfg.resolved_device in ("mps", "cuda", "cpu")
