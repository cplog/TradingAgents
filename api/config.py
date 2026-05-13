"""Service configuration loaded from environment variables.

DEFAULT_CONFIG already applies TRADINGAGENTS_* env-var overrides at import
time (see tradingagents/default_config.py).  This module copies that dict and
adds API-specific validation.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

from tradingagents.default_config import build_fresh_config


REQUIRED_API_KEYS = {
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "glm": "ZHIPU_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "minimax-cn": "MINIMAX_CN_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "kimi_code": "KIMI_CODE_API_KEY",
}


def _has_ollama_remote_auth() -> bool:
    token = bool(os.getenv("OLLAMA_CF_TOKEN", "").strip() or os.getenv("OLLAMA_API_KEY", "").strip())
    client_pair = bool(
        os.getenv("OLLAMA_CF_CLIENT_ID", "").strip()
        and os.getenv("OLLAMA_CF_CLIENT_SECRET", "").strip()
    )
    return token or client_pair


def build_service_config() -> Dict[str, Any]:
    """Return a config dict ready for TradingAgentsGraph.

    Rebuilds from env on each call so runtime ``os.environ`` updates (e.g.
    admin UI) can affect keys derived from ``TRADINGAGENTS_*`` variables.
    """
    return build_fresh_config()


def validate_api_key(config: Dict[str, Any]) -> None:
    """Raise RuntimeError if the chosen provider's API key is missing."""
    provider = config.get("llm_provider", "openai").lower()
    if provider == "ollama-remote" and not _has_ollama_remote_auth():
        raise RuntimeError(
            "Provider 'ollama-remote' requires remote auth. Set OLLAMA_CF_TOKEN "
            "or OLLAMA_API_KEY, or set both OLLAMA_CF_CLIENT_ID and OLLAMA_CF_CLIENT_SECRET."
        )
    env_var = REQUIRED_API_KEYS.get(provider)
    if env_var and not os.getenv(env_var):
        raise RuntimeError(
            f"Provider '{provider}' requires {env_var} to be set in the environment."
        )


def get_redacted_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of config safe to serialize (no secrets)."""
    safe = {k: v for k, v in config.items() if k not in ("api_key",)}
    return safe


def merge_request_config(
    base: Dict[str, Any],
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Deep copy ``base`` and apply ``overrides`` with one-level dict merge (matches dataflows ``set_config``).

    The API must not use shallow ``{**base, **overrides}``: nested dicts like ``data_vendors`` would
    alias ``base`` and concurrent jobs could corrupt shared state. The CLI runs one graph at a time.
    """
    from copy import deepcopy

    cfg = deepcopy(base)
    if not overrides:
        return cfg
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            inner = deepcopy(cfg[key])
            inner.update(deepcopy(value))
            cfg[key] = inner
        elif isinstance(value, dict):
            cfg[key] = deepcopy(value)
        else:
            cfg[key] = value
    return cfg
