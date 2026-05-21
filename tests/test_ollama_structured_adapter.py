"""The api-side Ollama structured-output adapter forces `with_structured_output`
onto json_schema (with json_mode fallback) for Ollama providers, while leaving
non-Ollama providers untouched.

Switching off function_calling is what stops the dimensions builder from
falling back to all-3/5 neutral pillars on nemotron/qwen3-via-Ollama runs.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from api.llm_clients import adapt_for_structured_output
from api.llm_clients.structured_output import _OllamaStructuredAdapter


def _fake_llm():
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value="bound")
    llm.invoke = MagicMock(return_value="ok")
    return llm


@pytest.mark.parametrize("provider", ["ollama", "ollama-local", "ollama-remote", "OLLAMA-REMOTE"])
def test_adapter_wraps_ollama_providers(provider):
    llm = _fake_llm()
    wrapped = adapt_for_structured_output(llm, provider)
    assert isinstance(wrapped, _OllamaStructuredAdapter)


@pytest.mark.parametrize("provider", ["openai", "deepseek", "openrouter", "minimax", ""])
def test_adapter_leaves_non_ollama_untouched(provider):
    llm = _fake_llm()
    out = adapt_for_structured_output(llm, provider)
    assert out is llm


def test_with_structured_output_uses_json_schema_for_ollama():
    llm = _fake_llm()
    wrapped = adapt_for_structured_output(llm, "ollama-remote")
    result = wrapped.with_structured_output(object)
    assert result == "bound"
    llm.with_structured_output.assert_called_once()
    _, kwargs = llm.with_structured_output.call_args
    assert kwargs["method"] == "json_schema"


def test_with_structured_output_falls_back_to_json_mode_if_json_schema_raises():
    """Defense-in-depth: bind-time errors from langchain (rare) cascade to
    json_mode rather than propagating, since json_mode works on every Ollama
    deployment including pre-0.5 builds.
    """
    llm = MagicMock()
    llm.with_structured_output = MagicMock(
        side_effect=[ValueError("schema rejected"), "bound-jsonmode"]
    )
    wrapped = adapt_for_structured_output(llm, "ollama-remote")
    out = wrapped.with_structured_output(object)
    assert out == "bound-jsonmode"
    assert llm.with_structured_output.call_count == 2
    methods = [call.kwargs["method"] for call in llm.with_structured_output.call_args_list]
    assert methods == ["json_schema", "json_mode"]


def test_caller_supplied_method_is_overridden():
    """The whole point of the wrapper is to ignore upstream method choices
    (function_calling from capabilities table) and force response_format."""
    llm = _fake_llm()
    wrapped = adapt_for_structured_output(llm, "ollama-remote")
    wrapped.with_structured_output(object, method="function_calling")
    _, kwargs = llm.with_structured_output.call_args
    assert kwargs["method"] == "json_schema"


def test_adapter_proxies_invoke_and_other_attrs():
    llm = _fake_llm()
    llm.model_name = "nemotron33b"
    wrapped = adapt_for_structured_output(llm, "ollama-remote")
    assert wrapped.invoke("hello") == "ok"
    assert wrapped.model_name == "nemotron33b"
    llm.invoke.assert_called_once_with("hello")
