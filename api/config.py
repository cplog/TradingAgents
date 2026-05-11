"""Service configuration loaded from environment variables.

Builds a resolved config dict by copying DEFAULT_CONFIG and overriding with
env vars, so a single .env file can drive the whole API service.
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

    Reads LLM_* and TRADINGAGENTS_* env vars and falls back to DEFAULT_CONFIG.
    """
    config = DEFAULT_CONFIG.copy()

    # LLM provider and models
    if os.getenv("LLM_PROVIDER"):
        config["llm_provider"] = os.getenv("LLM_PROVIDER")
    if os.getenv("DEEP_THINK_LLM"):
        config["deep_think_llm"] = os.getenv("DEEP_THINK_LLM")
    if os.getenv("QUICK_THINK_LLM"):
        config["quick_think_llm"] = os.getenv("QUICK_THINK_LLM")
    if os.getenv("BACKEND_URL"):
        config["backend_url"] = os.getenv("BACKEND_URL")

    # Provider-specific thinking config
    if os.getenv("GOOGLE_THINKING_LEVEL"):
        config["google_thinking_level"] = os.getenv("GOOGLE_THINKING_LEVEL")
    if os.getenv("OPENAI_REASONING_EFFORT"):
        config["openai_reasoning_effort"] = os.getenv("OPENAI_REASONING_EFFORT")
    if os.getenv("ANTHROPIC_EFFORT"):
        config["anthropic_effort"] = os.getenv("ANTHROPIC_EFFORT")

    # OpenRouter free-only flag
    if os.getenv("TRADINGAGENTS_OPENROUTER_FREE_ONLY", "").lower() in ("1", "true", "yes"):
        config["openrouter_free_only"] = True

    # Debate / recursion (already read by DEFAULT_CONFIG, but allow explicit override)
    if os.getenv("MAX_DEBATE_ROUNDS"):
        config["max_debate_rounds"] = int(os.getenv("MAX_DEBATE_ROUNDS"))
    if os.getenv("MAX_RISK_DISCUSS_ROUNDS"):
        config["max_risk_discuss_rounds"] = int(os.getenv("MAX_RISK_DISCUSS_ROUNDS"))
    if os.getenv("MAX_RECUR_LIMIT"):
        config["max_recur_limit"] = int(os.getenv("MAX_RECUR_LIMIT"))

    # Output language
    if os.getenv("OUTPUT_LANGUAGE"):
        config["output_language"] = os.getenv("OUTPUT_LANGUAGE")

    # Service tuning
    if os.getenv("MAX_CONCURRENCY"):
        config["max_concurrency"] = int(os.getenv("MAX_CONCURRENCY"))
    if os.getenv("JOB_TTL_HOURS"):
        config["job_ttl_hours"] = int(os.getenv("JOB_TTL_HOURS"))

    return config


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
