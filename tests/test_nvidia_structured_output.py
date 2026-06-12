"""NVIDIA NIM prefers JSON-schema structured output over tool calling."""

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.schemas import ResearchPlan
from tradingagents.llm_clients.openai_client import NvidiaChatOpenAI


@pytest.mark.unit
def test_nvidia_defaults_to_json_schema(monkeypatch):
    captured: dict[str, str | None] = {}

    def fake_ws(_self, _schema, *, method=None, **kwargs):
        captured["method"] = method
        return MagicMock()

    monkeypatch.setattr(
        "langchain_openai.ChatOpenAI.with_structured_output",
        fake_ws,
    )
    llm = NvidiaChatOpenAI(
        model="google/gemma-2-27b-it",
        api_key="test-key",
        base_url="https://integrate.api.nvidia.com/v1",
    )
    llm.with_structured_output(ResearchPlan)
    assert captured.get("method") == "json_schema"


@pytest.mark.unit
def test_nvidia_deepseek_id_falls_back_to_json_mode(monkeypatch):
    captured: dict[str, str | None] = {}

    def fake_ws(_self, _schema, *, method=None, **kwargs):
        captured["method"] = method
        return MagicMock()

    monkeypatch.setattr(
        "langchain_openai.ChatOpenAI.with_structured_output",
        fake_ws,
    )
    llm = NvidiaChatOpenAI(
        model="deepseek-chat",
        api_key="test-key",
        base_url="https://integrate.api.nvidia.com/v1",
    )
    llm.with_structured_output(ResearchPlan)
    assert captured.get("method") == "json_mode"


@pytest.mark.unit
def test_nvidia_minimax_thinking_still_uses_function_calling(monkeypatch):
    captured: dict[str, str | None] = {}

    def fake_ws(_self, _schema, *, method=None, **kwargs):
        captured["method"] = method
        return MagicMock()

    monkeypatch.setattr(
        "langchain_openai.ChatOpenAI.with_structured_output",
        fake_ws,
    )
    llm = NvidiaChatOpenAI(
        model="MiniMax-M2",
        api_key="test-key",
        base_url="https://integrate.api.nvidia.com/v1",
    )
    llm.with_structured_output(ResearchPlan)
    assert captured.get("method") == "function_calling"
