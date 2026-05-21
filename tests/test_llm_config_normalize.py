"""Unit tests for LLM provider/model alignment."""

from __future__ import annotations

import pytest

from api.config import merge_request_config
from api.llm_config_normalize import (
    model_matches_provider,
    normalize_llm_config,
    provenance_model_mismatch_warning,
)
from api.run_provenance import build_run_provenance


@pytest.mark.unit
def test_ollama_remote_rejects_gpt_models():
    assert not model_matches_provider("ollama-remote", "gpt-5.4")
    assert model_matches_provider("ollama-remote", "glm-4.7-flash:latest")


@pytest.mark.unit
def test_normalize_ollama_remote_replaces_openai_defaults():
    cfg = normalize_llm_config(
        {
            "llm_provider": "ollama-remote",
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "gpt-5.4-mini",
        }
    )
    assert cfg["deep_think_llm"] == "glm-4.7-flash:latest"
    assert cfg["quick_think_llm"] == "qwen3:latest"


@pytest.mark.unit
def test_merge_request_config_normalizes_partial_provider_override():
    base = {
        "llm_provider": "openai",
        "deep_think_llm": "gpt-5.4",
        "quick_think_llm": "gpt-5.4-mini",
    }
    merged = merge_request_config(base, {"llm_provider": "ollama-remote"})
    assert merged["llm_provider"] == "ollama-remote"
    assert merged["deep_think_llm"] == "glm-4.7-flash:latest"
    assert merged["quick_think_llm"] == "qwen3:latest"


@pytest.mark.unit
def test_build_run_provenance_warns_on_impossible_combo():
    prov = build_run_provenance(
        {
            "llm_provider": "ollama-remote",
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "gpt-5.4-mini",
        }
    )
    assert prov["llm_provider"] == "ollama-remote"
    assert any("do not match provider" in w for w in prov["bias_warnings"])


@pytest.mark.unit
def test_provenance_mismatch_warning_message():
    msg = provenance_model_mismatch_warning("ollama-remote", "gpt-5.4", "gpt-5.4-mini")
    assert msg is not None
    assert "ollama-remote" in msg
