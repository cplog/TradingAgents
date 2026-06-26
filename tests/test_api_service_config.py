"""Server config: LLM provider auto-resolution for background jobs."""

import pytest

from api.config import build_service_config


@pytest.mark.unit
def test_auto_resolve_llm_when_openai_unconfigured(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-placeholder")

    cfg = build_service_config()
    assert cfg["llm_provider"] == "deepseek"
    assert "deepseek" in cfg["quick_think_llm"].lower()


@pytest.mark.unit
def test_explicit_llm_provider_env_not_auto_replaced(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-other")

    cfg = build_service_config()
    assert cfg["llm_provider"] == "openai"
