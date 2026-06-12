"""Provider-aware structured-output adapter for dimensions LLM calls.

`tradingagents.llm_clients.capabilities` declares `function_calling` as the
default structured-output method, which is right for OpenAI/DeepSeek/etc. but
breaks for Ollama-served models: their OpenAI-compat layer ships tool-call
shapes unreliably, so LangChain's parser returns `None` and downstream code
falls back to neutral defaults (all pillars 3/5, all factors 50).

Ollama's `response_format` path (json_schema → json_mode) is much more
reliable, especially for the deeply nested `PillarScores` schema (4 pillars ×
4 sub-dimensions × {score, rationale}). This wrapper intercepts only
`with_structured_output` and re-binds it through `response_format`, leaving
plain `invoke` (used by the existing JSON fallback) untouched.

Lives in api/ to honor the fork rule on `tradingagents/`.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


_OLLAMA_PROVIDERS = ("ollama", "ollama-local", "ollama-remote")
_NVIDIA_PROVIDERS = ("nvidia",)


class _JsonSchemaStructuredAdapter:
    """Prefer response_format structured output over tool binding."""

    def __init__(self, llm: Any) -> None:
        self._llm = llm

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        kwargs.pop("method", None)
        try:
            return self._llm.with_structured_output(
                schema, method="json_schema", **kwargs
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.info(
                "json_schema bind rejected (%s); retrying json_mode",
                exc,
            )
            return self._llm.with_structured_output(
                schema, method="json_mode", **kwargs
            )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._llm, name)


class _OllamaStructuredAdapter(_JsonSchemaStructuredAdapter):
    """Backward-compatible alias for Ollama structured-output routing."""


def adapt_for_structured_output(llm: Any, provider: str) -> Any:
    """Return `llm` wrapped when tool-based structured output is unreliable.

    Ollama and NVIDIA NIM both reject LangChain's default function-calling
    binding; json_schema/json_mode via response_format is more reliable.
    """
    p = (provider or "").lower()
    if p in _OLLAMA_PROVIDERS or p in _NVIDIA_PROVIDERS:
        return _JsonSchemaStructuredAdapter(llm)
    return llm
