"""API-side LLM adapters that wrap upstream tradingagents/llm_clients output.

Lives in api/ (not tradingagents/) per the fork rule: new features go here so
upstream sync stays clean. Today there's only the structured-output adapter
that switches Ollama-served models off function_calling.
"""

from api.llm_clients.structured_output import adapt_for_structured_output

__all__ = ["adapt_for_structured_output"]
