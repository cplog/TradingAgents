"""Environment-driven configuration for the Kronos integration."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _resolve_device(preferred: str) -> str:
    """Map ``auto`` to ``mps`` → ``cuda`` → ``cpu``; pass explicit names through."""
    if preferred != "auto":
        return preferred
    try:
        import torch  # type: ignore
    except ImportError:
        return "cpu"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


@dataclass(frozen=True)
class KronosConfig:
    """Frozen view of all KRONOS_* env vars."""
    enabled: bool = True
    model: str = "NeoQuasar/Kronos-small"
    tokenizer: str = "NeoQuasar/Kronos-Tokenizer-base"
    device: str = "auto"
    lookback: int = 200
    pred_len: int = 20
    sample_count: int = 1
    temperature: float = 1.0
    top_p: float = 0.9
    timeout_seconds: int = 90
    max_context: int = 512

    @property
    def resolved_device(self) -> str:
        return _resolve_device(self.device)

    @classmethod
    def from_env(cls) -> "KronosConfig":
        return cls(
            enabled=_env_bool("KRONOS_ENABLED", True),
            model=os.getenv("KRONOS_MODEL", "NeoQuasar/Kronos-small"),
            tokenizer=os.getenv(
                "KRONOS_TOKENIZER", "NeoQuasar/Kronos-Tokenizer-base"
            ),
            device=os.getenv("KRONOS_DEVICE", "auto"),
            lookback=_env_int("KRONOS_LOOKBACK", 200),
            pred_len=_env_int("KRONOS_PRED_LEN", 20),
            sample_count=_env_int("KRONOS_SAMPLE_COUNT", 1),
            temperature=_env_float("KRONOS_T", 1.0),
            top_p=_env_float("KRONOS_TOP_P", 0.9),
            timeout_seconds=_env_int("KRONOS_TIMEOUT_SECONDS", 90),
            max_context=_env_int("KRONOS_MAX_CONTEXT", 512),
        )
