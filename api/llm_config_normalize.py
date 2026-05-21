"""Align llm_provider with deep/quick model names before runs and provenance."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional, Tuple

# Keep in sync with frontend/src/components/LlmPicker.tsx MODEL_PRESETS.
_PROVIDER_DEFAULT_MODELS: Dict[str, Tuple[str, str]] = {
    "openai": ("gpt-5.4", "gpt-5.4-mini"),
    "google": ("gemini-3.1-pro-preview", "gemini-3-flash-preview"),
    "anthropic": ("claude-opus-4-7", "claude-sonnet-4-6"),
    "deepseek": ("deepseek-v4-pro", "deepseek-v4-flash"),
    "openrouter": ("openrouter/free", "openrouter/free"),
    "moonshot": ("moonshot-v1-8k", "moonshot-v1-8k"),
    "xai": ("grok-4.20-reasoning", "grok-4.20-non-reasoning"),
    "qwen": ("qwen3.6-plus", "qwen3.6-flash"),
    "glm": ("glm-5.1", "glm-5-turbo"),
    "minimax": ("MiniMax-M2.7", "MiniMax-M2.7-highspeed"),
    "ollama": ("glm-4.7-flash:latest", "qwen3:latest"),
    "ollama-local": ("glm-4.7-flash:latest", "qwen3:latest"),
    "ollama-remote": ("glm-4.7-flash:latest", "qwen3:latest"),
}

_OPENAI_STYLE_PREFIXES = ("gpt-", "o1", "o3", "o4", "chatgpt")


def _looks_like_openai_catalog_model(model: str) -> bool:
    m = (model or "").strip().lower()
    if not m:
        return False
    return any(m.startswith(p) for p in _OPENAI_STYLE_PREFIXES)


def _looks_like_ollama_tag_model(model: str) -> bool:
    m = (model or "").strip().lower()
    return ":" in m or m.endswith(":latest")


def model_matches_provider(provider: Optional[str], model: Optional[str]) -> bool:
    """Return False when a model name is clearly from another provider's catalog."""
    p = (provider or "").strip().lower()
    m = (model or "").strip()
    if not p or not m:
        return True
    if p in ("ollama", "ollama-local", "ollama-remote"):
        return not _looks_like_openai_catalog_model(m)
    if p == "openai":
        return not _looks_like_ollama_tag_model(m)
    if p == "google":
        return "gemini" in m.lower()
    if p == "anthropic":
        return "claude" in m.lower()
    if p == "deepseek":
        return "deepseek" in m.lower()
    return True


def normalize_llm_config(config: Dict[str, Any], *, in_place: bool = False) -> Dict[str, Any]:
    """Replace cross-provider model names with provider defaults (env/UI mismatch fix)."""
    cfg = config if in_place else deepcopy(config)
    provider = str(cfg.get("llm_provider") or "").strip().lower()
    if not provider:
        return cfg
    defaults = _PROVIDER_DEFAULT_MODELS.get(provider)
    if not defaults:
        return cfg
    def_deep, def_quick = defaults
    deep = str(cfg.get("deep_think_llm") or "").strip()
    quick = str(cfg.get("quick_think_llm") or "").strip()
    if deep and not model_matches_provider(provider, deep):
        cfg["deep_think_llm"] = def_deep
    if quick and not model_matches_provider(provider, quick):
        cfg["quick_think_llm"] = def_quick
    return cfg


def provenance_model_mismatch_warning(
    provider: Optional[str],
    deep: Optional[str],
    quick: Optional[str],
) -> Optional[str]:
    """Human-readable warning when a stored snapshot has incompatible provider/models."""
    p = (provider or "").strip()
    d = (deep or "").strip()
    q = (quick or "").strip()
    if not p:
        return None
    bad: list[str] = []
    if d and not model_matches_provider(p, d):
        bad.append(d)
    if q and not model_matches_provider(p, q):
        bad.append(q)
    if not bad:
        return None
    models = " / ".join(dict.fromkeys(bad))
    return (
        f"Recorded models ({models}) do not match provider {p} — "
        "likely TRADINGAGENTS_LLM_PROVIDER without matching DEEP/QUICK model env vars"
    )
