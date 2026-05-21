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


class _OllamaStructuredAdapter:
    """Forward everything to the inner LLM except `with_structured_output`.

    For Ollama we want json_schema first (server-side schema enforcement on
    Ollama ≥0.5), then json_mode (universal OpenAI-compat baseline). Bind-time
    failures are rare — LangChain validates the method literal but does not
    talk to the provider — so this try/except is mostly defense-in-depth.
    """

    def __init__(self, llm: Any) -> None:
        self._llm = llm

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        # Strip caller-supplied method; the whole point of this wrapper is to
        # override the function_calling default.
        kwargs.pop("method", None)
        try:
            return self._llm.with_structured_output(
                schema, method="json_schema", **kwargs
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.info(
                "Ollama json_schema bind rejected (%s); retrying json_mode",
                exc,
            )
            return self._llm.with_structured_output(
                schema, method="json_mode", **kwargs
            )

    # Transparent proxy for everything else (invoke, model_name, kwargs, …).
    def __getattr__(self, name: str) -> Any:
        return getattr(self._llm, name)


def adapt_for_structured_output(llm: Any, provider: str) -> Any:
    """Return `llm` wrapped if `provider` is Ollama-style; else unchanged.

    Wrapping is cheap and transparent — non-dimensions code paths that use
    `llm.invoke(...)` or `llm.bind_tools(...)` see the same object behavior.
    Only `with_structured_output` is intercepted.
    """
    if (provider or "").lower() in _OLLAMA_PROVIDERS:
        return _OllamaStructuredAdapter(llm)
    return llm
