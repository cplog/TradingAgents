import copy
import os

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

# Single source of truth for env-var -> config-key overrides. To expose
# a new config key for environment-based override, add a row here.
_ENV_OVERRIDES = {
    "TRADINGAGENTS_LLM_PROVIDER": "llm_provider",
    "TRADINGAGENTS_DEEP_THINK_LLM": "deep_think_llm",
    "TRADINGAGENTS_QUICK_THINK_LLM": "quick_think_llm",
    "TRADINGAGENTS_LLM_BACKEND_URL": "backend_url",
    "TRADINGAGENTS_OUTPUT_LANGUAGE": "output_language",
    "TRADINGAGENTS_MAX_DEBATE_ROUNDS": "max_debate_rounds",
    "TRADINGAGENTS_MAX_RISK_ROUNDS": "max_risk_discuss_rounds",
    "TRADINGAGENTS_MAX_RECUR_LIMIT": "max_recur_limit",
    "TRADINGAGENTS_CHECKPOINT_ENABLED": "checkpoint_enabled",
    "TRADINGAGENTS_BENCHMARK_TICKER": "benchmark_ticker",
    "TRADINGAGENTS_OPENROUTER_FREE_ONLY": "openrouter_free_only",
    "TRADINGAGENTS_MAX_CONCURRENCY": "max_concurrency",
    "TRADINGAGENTS_JOB_TTL_HOURS": "job_ttl_hours",
    "TRADINGAGENTS_TEMPERATURE": "temperature",
    "TRADINGAGENTS_DIMENSIONS_ENABLED": "dimensions_enabled",
    "TRADINGAGENTS_DIMENSIONS_IN_GRAPH": "dimensions_in_graph",
    "TRADINGAGENTS_PREFER_FREE_DATA_VENDORS": "prefer_free_data_vendors",
    "TRADINGAGENTS_DATA_CACHE_BACKEND": "data_cache_backend",
    "TRADINGAGENTS_DATA_CACHE_AUTO_STOCK_BARS": "data_cache_auto_stock_bars",
    "TRADINGAGENTS_MONITOR_ENABLED": "monitor_enabled",
    "TRADINGAGENTS_MONITOR_POLL_SECONDS": "monitor_poll_seconds",
    "TRADINGAGENTS_MONITOR_SIGNAL_THRESHOLD": "monitor_signal_threshold",
    "TRADINGAGENTS_MONITOR_SPREAD_MAX_PCT": "monitor_spread_max_pct",
    "TRADINGAGENTS_MONITOR_COOLDOWN_MINUTES": "monitor_cooldown_minutes",
    "TRADINGAGENTS_PARALLEL_ANALYSTS": "parallel_analysts",
    "TRADINGAGENTS_SEMANTIC_DEBATE_TERMINATION": "semantic_debate_termination",
    "TRADINGAGENTS_LLM_TIMEOUT_SECONDS": "llm_timeout_seconds",
    "TRADINGAGENTS_JOB_TIMEOUT_SECONDS": "job_timeout_seconds",
    "TRADINGAGENTS_JOB_STUCK_SECONDS": "job_stuck_seconds",
    "TRADINGAGENTS_OPTIONS_STRATEGIST_ENABLED": "options_strategist_enabled",
    "TRADINGAGENTS_REGIME_PREFILTER_ENABLED": "regime_prefilter_enabled",
    "TRADINGAGENTS_REGIME_PREFILTER_MODE": "regime_prefilter_mode",
    "TRADINGAGENTS_REGIME_ENFORCE_THRESHOLD": "regime_enforce_threshold",
    "TRADINGAGENTS_MIN_CONFIDENCE_FOR_PRODUCTION": "min_confidence_for_production",
    "TRADINGAGENTS_DEBATE_SCORER_ENABLED": "debate_scorer_enabled",
}


def _coerce(value: str, reference):
    """Coerce env-var string to the type of the existing default value."""
    if isinstance(reference, bool):
        return value.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    # Env-only keys whose template default is None (e.g. llm_temperature)
    if reference is None:
        try:
            return float(value)
        except ValueError:
            return value
    return value


def _apply_env_overrides(config: dict) -> dict:
    """Apply TRADINGAGENTS_* env vars to the config dict in-place."""
    for env_var, key in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None or raw == "":
            continue
        config[key] = _coerce(raw, config.get(key))
    return config


_CONFIG_BASE: dict = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_log_path": os.getenv(
        "TRADINGAGENTS_MEMORY_LOG_PATH",
        os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md"),
    ),
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.5",
    "quick_think_llm": "gpt-5.4-mini",
    # When None, each provider's client falls back to its own default endpoint.
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,
    "openai_reasoning_effort": None,
    "anthropic_effort": None,
    # Sampling temperature, forwarded to every provider when set. None leaves
    # each provider at its own default. Lower values reduce run-to-run
    # variation on models that honor it; reasoning models largely ignore it.
    "temperature": None,
    # HTTP timeout (seconds) for LLM requests. None leaves each provider at
    # its own default. For Ollama behind Cloudflare, the client auto-defaults
    # to 90 s to stay under Cloudflare's 120 s proxy timeout.
    "llm_timeout_seconds": None,
    # Checkpoint/resume: when True, LangGraph saves state after each node.
    "checkpoint_enabled": False,
    # Output language for analyst reports and final decision
    "output_language": os.getenv("OUTPUT_LANGUAGE", "English"),
    # Debate and discussion settings
    "max_debate_rounds": 2,
    "max_risk_discuss_rounds": 2,
    # When True, a Debate Scorer node runs after the bull/bear debate and before
    # the Research Manager, providing structured scores that break ties.
    "debate_scorer_enabled": True,
    "max_recur_limit": 100,
    # News / data fetching parameters
    "news_article_limit": 20,
    "global_news_article_limit": 10,
    "global_news_lookback_days": 7,
    "global_news_queries": [
        "Federal Reserve interest rates inflation",
        "S&P 500 earnings GDP economic outlook",
        "geopolitical risk trade war sanctions",
        "ECB Bank of England BOJ central bank policy",
        "oil commodities supply chain energy",
    ],
    # When True, the CLI limits OpenRouter model selection to free-tier models
    "openrouter_free_only": False,
    # Service settings (API mode)
    "max_concurrency": 3,
    "job_ttl_hours": 24,
    # Wall-clock cap for a single API job (seconds). None disables the cap.
    "job_timeout_seconds": 7200,
    # Heartbeat warning when no graph step completes for this many seconds.
    "job_stuck_seconds": 900,
    # Data vendor configuration (comma-separated primaries; see prefer_free_data_vendors).
    "prefer_free_data_vendors": True,
    "data_vendors": {
        "core_stock_apis": "yfinance,finnhub,alpha_vantage",
        "technical_indicators": "yfinance,alpha_vantage",
        "fundamental_data": "yfinance,alpha_vantage",
        "news_data": "yfinance,finnhub,google_rss,akshare,alpha_vantage",
        "macro_data": "akshare",
        "options_data": "yfinance",
    },
    "tool_vendors": {},
    # Options strategist overlay (runs after Portfolio Manager)
    "options_strategist_enabled": False,
    # Hard Penny Market (HPM) regime pre-filter (Phase 1)
    "regime_prefilter_enabled": False,
    "regime_prefilter_mode": "observe",  # observe | enforce
    "regime_enforce_threshold": 2.5,
    # Minimum confidence (0..1) required before a run is considered safe for
    # downstream trading-system consumption. Runs below this threshold are still
    # saved and displayed, but flagged with production_gated=True.
    "min_confidence_for_production": 0.60,
    "regime_topic_multipliers": {
        "default": 1.0,
        "momentum": 1.0,
        "growth": 1.0,
        "value": 1.0,
        "defensive": 1.0,
        "speculative": 1.0,
    },
    # Benchmark for alpha calculation in the reflection layer.
    "benchmark_ticker": None,
    "benchmark_map": {
        ".NS": "^NSEI",
        ".BO": "^BSESN",
        ".T": "^N225",
        ".HK": "^HSI",
        ".L": "^FTSE",
        ".TO": "^GSPTSE",
        ".AX": "^AXJO",
        "": "SPY",
    },
    # Standardized stock dimensions (API UX / peer-aware factors)
    "dimensions_enabled": True,
    # When True, run one dimensions build inside LangGraph after analysts (feeds PM/trader).
    "dimensions_in_graph": True,
    # Optional TradingAgents data cache: none | sqlite | d1 (Cloudflare D1 REST, same env as API).
    "data_cache_backend": "none",
    "data_cache_sqlite_filename": "ta_data_cache.db",
    # Hot-board JSON API base (NewsNow-compatible ``GET /api/s?id=``). None disables outbound fetch.
    "hot_news_feed_base_url": os.getenv("TRADINGAGENTS_HOT_NEWS_FEED_BASE_URL") or None,
    "hot_news_feed_timeout_sec": 30,
    "hot_news_memory_ttl_sec": 300,
    # When True with sqlite/d1 cache: persist parsed OHLCV after each successful get_stock_data.
    "data_cache_auto_stock_bars": False,
    # Override vendor tag stored on ta_stock_bars (default: primary configured core_stock_apis vendor).
    "data_cache_stock_vendor_tag": None,
    # When True, analysts run in parallel via LangGraph Send (reduces wall-clock latency).
    "parallel_analysts": False,
    # When True, debates can terminate early if the LLM detects convergence (saves tokens).
    "semantic_debate_termination": False,
    # Overnight monitor (daily barbell; free yfinance + AKShare)
    "monitor_enabled": False,
    "monitor_poll_seconds": 900,
    "monitor_signal_threshold": 75,
    "monitor_spread_max_pct": 8.0,
    "monitor_cooldown_minutes": 30,
    "monitor_min_drop_pct": -10.0,
}


def build_fresh_config() -> dict:
    """Return a new config dict with current TRADINGAGENTS_* env applied."""
    return _apply_env_overrides(copy.deepcopy(_CONFIG_BASE))


DEFAULT_CONFIG = build_fresh_config()
