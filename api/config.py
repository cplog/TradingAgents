"""Service configuration loaded from environment variables.

DEFAULT_CONFIG already applies TRADINGAGENTS_* env-var overrides at import
time (see tradingagents/default_config.py).  This module copies that dict and
adds API-specific validation.
"""
from __future__ import annotations

import os
from typing import Dict, Any

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

from tradingagents.default_config import DEFAULT_CONFIG


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


def build_service_config() -> Dict[str, Any]:
    """Return a config dict ready for TradingAgentsGraph.

    DEFAULT_CONFIG already reflects TRADINGAGENTS_* env vars.  We just copy
    it here so the caller gets a mutable snapshot.
    """
    return DEFAULT_CONFIG.copy()


def validate_api_key(config: Dict[str, Any]) -> None:
    """Raise RuntimeError if the chosen provider's API key is missing."""
    provider = config.get("llm_provider", "openai").lower()
    env_var = REQUIRED_API_KEYS.get(provider)
    if env_var and not os.getenv(env_var):
        raise RuntimeError(
            f"Provider '{provider}' requires {env_var} to be set in the environment."
        )


def get_redacted_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of config safe to serialize (no secrets)."""
    safe = {k: v for k, v in config.items() if k not in ("api_key",)}
    return safe
