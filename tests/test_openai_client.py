"""Tests for the OpenAI-compatible LLM client."""

from __future__ import annotations

import warnings

import pytest

from tradingagents.llm_clients import create_llm_client
from tradingagents.llm_clients.openai_client import OpenAIClient


@pytest.mark.unit
def test_openai_custom_endpoint_allows_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = OpenAIClient(
        model="kimi-k2.6",
        base_url="http://127.0.0.1:5199/v1",
        provider="openai",
    )
    llm = client.get_llm()
    assert llm.openai_api_base == "http://127.0.0.1:5199/v1"
    assert llm.openai_api_key.get_secret_value() == "EMPTY"


@pytest.mark.unit
def test_openai_official_endpoint_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = OpenAIClient(model="gpt-5.4-mini", provider="openai")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        client.get_llm()


@pytest.mark.unit
def test_openai_custom_endpoint_suppresses_unknown_model_warning(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = OpenAIClient(
        model="kimi-k2.6",
        base_url="http://127.0.0.1:5199/v1",
        provider="openai",
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        client.get_llm()
    runtime_warnings = [w for w in caught if issubclass(w.category, RuntimeWarning)]
    assert not runtime_warnings


@pytest.mark.unit
def test_moonshot_provider_alias_resolves(monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-test")
    client = create_llm_client("moonshot", "kimi-k2.6")
    assert isinstance(client, OpenAIClient)
    assert client.provider == "moonshot"
    llm = client.get_llm()
    assert llm.openai_api_base == "https://api.moonshot.ai/v1"
